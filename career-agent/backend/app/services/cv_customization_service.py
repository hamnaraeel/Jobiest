"""Orchestrates CV generation: plan -> content -> deterministic validation
-> assembly. Exactly two LLM calls (planning, content), each validated
against a Pydantic schema and retried once on malformed output; content is
additionally checked against the Career Profile and retried once more if
it contains anything unsupported, then deterministically sanitized
regardless of whether the retry fully fixed it. The score, the source
traceability, and the final claim of "verified" never depend on what the
LLM said about itself.

Tailoring a CV to a specific job is deliberately narrow: the candidate's
full profile -- every experience, every project, every existing bullet,
all education/certifications/achievements/research, and their entire
Technical Skills list -- is always included, verbatim, in
assemble_cv_content(). Nothing here ever omits an entry as "not relevant
enough" or rewrites a bullet's wording. Per the user's standing ~95%-
preservation instruction, the only thing an LLM ever authors is the
summary (generate_cv_content()); skill emphasis is tailored per job too,
but deterministically by reordering the candidate's own stored skill
categories toward the job's requirements -- never by an LLM selecting,
adding, or dropping skills (see _master_skill_categories() and
_reorder_skills_for_job())."""

import json
import logging
import re

from pydantic import BaseModel, ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai.client import STRUCTURED_OUTPUT_MAX_TOKENS, get_ai_client, get_ai_extra_params, get_ai_model
from app.ai.cv_prompts import CV_PLAN_PROMPT_V1, CV_SUMMARY_PROMPT_V1
from app.ai.cv_structured_outputs import CVContentOutput, CVPlanOutput
from app.config import get_settings
from app.models.cv_change import CVChange
from app.models.cv_section import CVSection
from app.models.cv_version import CVVersion
from app.models.enums import CVSectionType, CVStatus, EntityType, SkillCategory
from app.models.job import Job
from app.models.job_match import JobMatch
from app.schemas.cv import (
    CVAchievementEntry,
    CVBullet,
    CVCertificationEntry,
    CVContent,
    CVEducationEntry,
    CVExperienceEntry,
    CVHeader,
    CVProjectEntry,
    CVResearchEntry,
    CVSkillCategory,
)
from app.schemas.cv_generation import CVPlan, ValidationIssue
from app.services import cv_comparison_service, cv_render_service
from app.services.cv_validation_service import validate_summary
from app.services.job_matching_service import (
    ProfileContext,
    compute_match,
    get_relevant_career_data,
    lookup_skill,
    normalize_skill,
)
from app.services.profile_service import get_default_profile

logger = logging.getLogger("app.cv_customization")

# Fixed, not AI-decided -- there is no longer a "which sections earn a
# place on this CV" question (every section with any profile data is
# always included), only a stable rendering order.
DEFAULT_SECTION_ORDER = [
    CVSectionType.SUMMARY, CVSectionType.SKILLS, CVSectionType.EXPERIENCE, CVSectionType.PROJECTS,
    CVSectionType.RESEARCH, CVSectionType.EDUCATION, CVSectionType.CERTIFICATIONS, CVSectionType.ACHIEVEMENTS,
]


class CVGenerationInputError(ValueError):
    pass


class AIResponseError(RuntimeError):
    pass


def _call_structured(client, model: str, system_prompt: str, user_content: str, schema: type[BaseModel], max_retries: int = 1):
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]
    last_error = "unknown error"

    for attempt in range(max_retries + 1):
        try:
            completion = client.chat.completions.parse(
                model=model,
                messages=messages,
                response_format=schema,
                max_tokens=STRUCTURED_OUTPUT_MAX_TOKENS,
                **get_ai_extra_params(),
            )
        except Exception as exc:
            last_error = f"OpenAI request failed: {exc}"
            completion = None

        if completion is not None:
            parsed = completion.choices[0].message.parsed
            if parsed is not None:
                try:
                    return schema.model_validate(parsed.model_dump())
                except ValidationError as exc:
                    last_error = f"AI response failed schema validation: {exc}"
            else:
                refusal = getattr(completion.choices[0].message, "refusal", None)
                last_error = f"Model did not return structured output: {refusal or 'unknown reason'}"

        if attempt < max_retries:
            logger.warning("structured output call failed (attempt %d), retrying: %s", attempt + 1, last_error)
            messages.append({
                "role": "user",
                "content": f"Your previous response was invalid: {last_error}. Strictly follow the "
                           f"required JSON schema and try again.",
            })

    raise AIResponseError(last_error)


def _compact_requirements(job: Job) -> list[dict]:
    return [
        {"text": r.requirement_text, "category": r.category.value, "required": r.required, "skill_name": r.skill_name}
        for r in job.requirements
    ]


def _compact_profile_for_planning(ctx: ProfileContext) -> dict:
    return {
        "experiences": [{"company": e.company, "role": e.role, "technologies": e.technologies, "skills": e.skills} for e in ctx.experiences],
        "projects": [{"name": p.name, "technologies": p.technologies, "skills": p.skills} for p in ctx.projects],
        "verified_skills": sorted(name for name, ev in ctx.skill_index.items() if ev.verified),
    }


def generate_cv_plan(client, model: str, job: Job, ctx: ProfileContext) -> CVPlan:
    payload = json.dumps({
        "job": {"title": job.title, "company": job.company, "requirements": _compact_requirements(job)},
        "profile": _compact_profile_for_planning(ctx),
    })
    output: CVPlanOutput = _call_structured(client, model, CV_PLAN_PROMPT_V1, payload, CVPlanOutput)

    return CVPlan(
        target_role=output.target_role or (job.title or "the target role"),
        priority_skills=[s for s in output.priority_skills if lookup_skill(ctx, s) is not None],
        reasoning=output.reasoning,
    )


def _compact_profile_for_content(ctx: ProfileContext, plan: CVPlan) -> dict:
    """Unlike the planning payload, no ids are needed here -- there is no
    selection step left to reference them. The summary is the only thing
    this call produces (skills are handled deterministically, never by
    the LLM -- see _master_skill_categories())."""
    return {
        "priority_skills": plan.priority_skills,
        "verified_skills": sorted(name for name, ev in ctx.skill_index.items() if ev.verified),
        "experiences": [
            {"company": e.company, "role": e.role, "technologies": e.technologies, "bullets": [b.bullet for b in e.bullets]}
            for e in ctx.experiences
        ],
        "projects": [
            {"name": p.name, "technologies": p.technologies, "results": [r.description for r in p.results]}
            for p in ctx.projects
        ],
    }


def _validate_content(content: CVContentOutput, ctx: ProfileContext, job: Job, plan: CVPlan) -> list[ValidationIssue]:
    watch_terms = [r.skill_name or r.requirement_text for r in job.requirements] + plan.priority_skills
    return validate_summary(content.summary, ctx, watch_terms)


def generate_cv_content(client, model: str, job: Job, plan: CVPlan, ctx: ProfileContext) -> tuple[CVContentOutput, list[ValidationIssue]]:
    system_prompt = CV_SUMMARY_PROMPT_V1
    payload = json.dumps({
        "job": {"title": job.title, "company": job.company, "target_role": plan.target_role},
        "profile": _compact_profile_for_content(ctx, plan),
    })

    output = _call_structured(client, model, system_prompt, payload, CVContentOutput)
    issues = _validate_content(output, ctx, job, plan)

    if issues:
        correction = (
            "The following items were rejected as unsupported by the career profile and must not "
            "appear in a corrected response: " + "; ".join(i.message for i in issues) +
            ". Regenerate using only the given profile data."
        )
        output = _call_structured(client, model, system_prompt, payload + "\n\nCORRECTION:\n" + correction, CVContentOutput)
        issues = _validate_content(output, ctx, job, plan)

    return output, issues


# --- Deterministic skill tailoring -----------------------------------------
#
# Per the user's standing "MASTER CV" instruction: the Technical Skills
# section is never regenerated or reselected by an LLM. It is always the
# candidate's full, verified skill list, grouped by each skill's own
# stored category (set once at resume-import time) -- that grouping *is*
# the master Skills section and every skill in it always appears on every
# generated CV. The only thing that varies per job is ordering: skills
# and categories that match this job's requirements are promoted toward
# the top (a stable sort, so nothing else about the order changes). No
# skill is ever added, removed, or renamed.


def _master_skill_categories(ctx: ProfileContext) -> list[dict]:
    # `Skill.verified` is a separate manual evidence-confirmation flag
    # (see VerifiableMixin) that resume import always leaves False --
    # it does not mean "not really in the candidate's resume." Every
    # other section of the CV (experience, projects, education, ...)
    # already includes the full profile regardless of that flag; Skills
    # follows the same rule for consistency, since it's still the
    # candidate's own master data.
    by_category: dict[SkillCategory, list[str]] = {}
    for skill in ctx.profile.skills:
        by_category.setdefault(skill.category, []).append(skill.name)
    return [{"category": cat.value, "skills": by_category[cat]} for cat in SkillCategory if cat in by_category]


def _reorder_skills_for_job(master_categories: list[dict], job: Job, plan: CVPlan) -> list[dict]:
    # Job requirements are often full sentences ("Strong familiarity with
    # PyTorch"), not bare skill names, so relevance is substring
    # containment (same convention as cv_validation_service.matching_terms)
    # rather than an exact-match set -- otherwise a short skill name like
    # "PyTorch" would never match a longer requirement sentence.
    watch_terms = [r.skill_name or r.requirement_text for r in job.requirements] + plan.priority_skills
    haystack = f" {' '.join(normalize_skill(t) for t in watch_terms if t)} "

    def is_relevant(skill_name: str) -> bool:
        term = normalize_skill(skill_name)
        return bool(term) and f" {term} " in haystack

    categories = [
        {
            "category": cat["category"],
            "skills": sorted(cat["skills"], key=lambda s: not is_relevant(s)),
            "has_relevant": any(is_relevant(s) for s in cat["skills"]),
        }
        for cat in master_categories
    ]
    categories.sort(key=lambda c: not c["has_relevant"])
    return [{"category": c["category"], "skills": c["skills"]} for c in categories]


# Deterministic (not AI-decided): a project's own already-recorded skill
# tags are what put it in "Research & ML" vs "Engineering & Full-Stack" on
# the rendered CV -- grouping never depends on the job being applied to,
# so which category a project lands in never changes between generations.
_RESEARCH_ML_SKILL_TAGS = {"ml/dl", "nlp", "computer vision", "llm"}


def _project_category(proj) -> str:
    tags = {s.lower() for s in proj.skills}
    if tags & _RESEARCH_ML_SKILL_TAGS:
        return "Research & ML"
    return "Engineering & Full-Stack"


_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")


def _project_bullets(proj) -> list[CVBullet]:
    """One bullet per sentence of the project's own stored description --
    a mechanical split on sentence boundaries, never a rewrite, so the
    candidate's exact wording always survives verbatim on the CV. Falls
    back to the project's quantified results only when there's no
    description recorded at all (some projects only have those)."""
    if proj.description:
        sentences = [s.strip() for s in _SENTENCE_SPLIT_RE.split(proj.description.strip()) if s.strip()]
        return [
            CVBullet(text=s, source_type=EntityType.PROJECT, source_id=proj.id, verified=proj.verified)
            for s in sentences
        ]
    return [
        CVBullet(
            text=f"{r.description} {r.metric or ''}".strip(),
            source_type=EntityType.PROJECT_RESULT, source_id=r.id, verified=r.verified,
        )
        for r in proj.results
    ]


def _cv_header(ctx: ProfileContext) -> CVHeader:
    profile = ctx.profile
    location = ", ".join(filter(None, [profile.city, profile.country])) or None
    return CVHeader(
        name=profile.full_name,
        # The candidate's own stated title -- never the AI-tailored
        # target_role, which could otherwise put a job posting's exact
        # wording directly under the candidate's name unsupported.
        tagline=profile.professional_title,
        email=profile.email,
        phone=profile.phone,
        linkedin=profile.linkedin_url,
        github=profile.github_url,
        portfolio=profile.portfolio_url,
        location=location,
    )


def assemble_cv_content(
    job: Job, plan: CVPlan, content: CVContentOutput, skill_categories: list[dict], ctx: ProfileContext
) -> CVContent:
    """The candidate's full profile, always -- every experience (with
    every bullet), every project (with every result), all research/
    education/certifications/achievements, and every verified skill,
    verbatim. Tailoring to `job` touches only `content.summary` and the
    ordering of `skill_categories` (see _reorder_skills_for_job); nothing
    here ever omits a profile entry or a skill based on the job."""

    experience_entries = [
        CVExperienceEntry(
            experience_id=exp.id, company=exp.company, role=exp.role, location=exp.location,
            start_date=exp.start_date, end_date=exp.end_date, currently_working=exp.currently_working,
            bullets=[
                CVBullet(text=b.bullet, source_type=EntityType.EXPERIENCE_BULLET, source_id=b.id, verified=b.verified)
                for b in exp.bullets
            ],
        )
        for exp in ctx.experiences
    ]

    project_entries = [
        CVProjectEntry(
            project_id=proj.id, name=proj.name, category=_project_category(proj),
            technologies=proj.technologies, github_url=proj.github_url, demo_url=proj.demo_url,
            bullets=_project_bullets(proj),
        )
        for proj in ctx.projects
    ]

    research_entries = [
        CVResearchEntry(
            research_id=r.id, title=r.title, research_area=r.research_area,
            technologies=r.technologies, description=r.description,
        )
        for r in ctx.research_items
    ]

    education_entries = [
        CVEducationEntry(
            education_id=e.id, institution=e.institution, degree=e.degree, field=e.field,
            start_date=e.start_date, end_date=e.end_date, grade=e.grade,
        )
        for e in ctx.educations
    ]

    certification_entries = [
        CVCertificationEntry(certification_id=c.id, name=c.name, issuer=c.issuer, issue_date=c.issue_date)
        for c in ctx.certifications
    ]

    achievement_entries = [
        CVAchievementEntry(achievement_id=a.id, title=a.title, description=a.description, metric=a.metric)
        for a in ctx.achievements
    ]

    return CVContent(
        header=_cv_header(ctx),
        summary=content.summary,
        skills=[CVSkillCategory(category=c["category"], skills=c["skills"]) for c in skill_categories],
        experience=experience_entries,
        projects=project_entries,
        research=research_entries,
        education=education_entries,
        certifications=certification_entries,
        achievements=achievement_entries,
        section_order=DEFAULT_SECTION_ORDER,
    )


def _fallback_summary(plan: CVPlan, ctx: ProfileContext) -> str:
    """Used only if the AI's summary still contains an unsupported claim
    after the correction retry -- guarantees the shipped summary can never
    carry a hallucinated technology, even in the worst case."""

    profile = ctx.profile
    skills = ", ".join(plan.priority_skills[:4])
    role = plan.target_role or profile.professional_title
    if skills:
        return f"{role} with experience in {skills}."
    return f"{role}."


def generate_cv(db: Session, job: Job, template_name: str = "ats/ml_engineer", compile_pdf_flag: bool = True) -> CVVersion:
    """The full Step 3 pipeline: JOB -> JOB MATCH -> CAREER PROFILE (in
    full) -> CV plan (framing only) -> CV content (summary + skill
    selection) -> validate -> reject unsupported claims -> LaTeX -> PDF ->
    store CV version."""

    profile = get_default_profile(db)
    if profile is None:
        raise CVGenerationInputError("No career profile exists yet -- create one before generating a CV.")
    if not job.requirements:
        raise CVGenerationInputError("This job has no extracted requirements yet -- analyze it first.")

    existing_match = db.execute(select(JobMatch).where(JobMatch.job_id == job.id)).scalar_one_or_none()
    if existing_match is None:
        existing_match = compute_match(db, job, use_ai_explanation=False)
    match_score_before = existing_match.overall_score

    settings = get_settings()
    client = get_ai_client()
    model = get_ai_model()
    ctx = get_relevant_career_data(db, profile.id)

    plan = generate_cv_plan(client, model, job, ctx)
    output, issues = generate_cv_content(client, model, job, plan, ctx)

    summary_has_unsupported_claim = any(i.code == "UNSUPPORTED_TECHNOLOGY_IN_SUMMARY" for i in issues)
    final_summary = _fallback_summary(plan, ctx) if summary_has_unsupported_claim else output.summary

    skill_categories = _reorder_skills_for_job(_master_skill_categories(ctx), job, plan)
    sanitized = {"summary": final_summary, "skills": skill_categories}

    content = assemble_cv_content(job, plan, output.model_copy(update={"summary": final_summary}), skill_categories, ctx)

    version_number = db.execute(
        select(func.count(CVVersion.id)).where(CVVersion.job_id == job.id)
    ).scalar_one() + 1
    version_name = f"{job.title or 'Role'} - {job.company or 'Company'} - V{version_number}"

    latex_source = cv_render_service.render_cv_to_latex(content, template_name)

    pdf_path = None
    compile_warnings: list[str] = []
    if compile_pdf_flag:
        result = cv_render_service.compile_pdf(latex_source, job.id, version_number)
        if result.success:
            pdf_path = result.pdf_path
            # Length is a target, never a reason to cut verified content.
            # One page beyond the target is allowed without comment ("2
            # pages when necessary"); only flag going further than that,
            # and only as a warning -- nothing is ever trimmed to fit.
            page_count = cv_render_service.count_pdf_pages(pdf_path)
            if page_count > settings.cv_max_pages + 1:
                compile_warnings.append(
                    f"CV is {page_count} page(s), exceeding the configured target of "
                    f"{settings.cv_max_pages} (+1 page tolerance). Content was not trimmed to force a shorter CV."
                )
        else:
            compile_warnings.append(f"PDF compilation failed: {result.error}")
            if result.log_excerpt:
                logger.error("pdflatex log excerpt for job_id=%s v%d:\n%s", job.id, version_number, result.log_excerpt)

    content_dump = content.model_dump(mode="json")
    all_warnings = [i.message for i in issues] + compile_warnings
    status = CVStatus.VALIDATED if not all_warnings and (pdf_path or not compile_pdf_flag) else CVStatus.DRAFT

    cv_version = CVVersion(
        job_id=job.id, profile_id=profile.id,
        version_name=version_name, version_number=version_number, template_name=template_name,
        status=status,
        summary=content.summary,
        skills=content_dump["skills"], experience=content_dump["experience"], projects=content_dump["projects"],
        education=content_dump["education"], certifications=content_dump["certifications"],
        research=content_dump["research"], achievements=content_dump["achievements"],
        latex_source=latex_source, pdf_path=pdf_path,
        match_score_before=match_score_before, match_score_after=None,
        warnings=all_warnings,
    )
    db.add(cv_version)
    db.flush()

    for i, section_type in enumerate(content.section_order):
        db.add(CVSection(cv_version_id=cv_version.id, section_type=section_type, sort_order=i))

    for change in cv_comparison_service.build_cv_changes(plan, sanitized, ctx):
        change.cv_version_id = cv_version.id
        db.add(change)

    db.commit()
    db.refresh(cv_version)

    after_match = compute_match(db, job, use_ai_explanation=False)
    cv_version.match_score_after = after_match.overall_score
    db.commit()
    db.refresh(cv_version)

    logger.info(
        "cv generated job_id=%s version=%d status=%s warnings=%d",
        job.id, version_number, status.value, len(all_warnings),
    )
    return cv_version
