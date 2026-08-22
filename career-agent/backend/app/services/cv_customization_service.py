"""Orchestrates CV generation: plan -> content -> deterministic validation
-> assembly. Exactly two LLM calls (planning, content), each validated
against a Pydantic schema and retried once on malformed output; content is
additionally checked against the Career Profile and retried once more if
it contains anything unsupported, then deterministically sanitized
regardless of whether the retry fully fixed it. The score, the source
traceability, and the final claim of "verified" never depend on what the
LLM said about itself.
"""

import json
import logging

from pydantic import BaseModel, ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai.client import get_ai_client, get_ai_model
from app.ai.cv_prompts import (
    CV_BULLET_REWRITE_PROMPT_V1,
    CV_PLAN_PROMPT_V1,
    CV_PROJECT_SELECTION_PROMPT_V1,
    CV_SKILL_SELECTION_PROMPT_V1,
    CV_SUMMARY_PROMPT_V1,
)
from app.ai.cv_structured_outputs import CVContentOutput, CVPlanOutput
from app.config import get_settings
from app.models.cv_change import CVChange
from app.models.cv_section import CVSection
from app.models.cv_version import CVVersion
from app.models.enums import CVSectionType, CVStatus, EntityType
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
from app.services.cv_validation_service import validate_bullets, validate_skill_categories, validate_summary
from app.services.job_matching_service import ProfileContext, compute_match, get_relevant_career_data, lookup_skill
from app.services.profile_service import get_default_profile

logger = logging.getLogger("app.cv_customization")


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
            completion = client.chat.completions.parse(model=model, messages=messages, response_format=schema)
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
        "experiences": [
            {"id": e.id, "company": e.company, "role": e.role, "technologies": e.technologies, "skills": e.skills}
            for e in ctx.experiences
        ],
        "projects": [
            {"id": p.id, "name": p.name, "technologies": p.technologies, "skills": p.skills}
            for p in ctx.projects
        ],
        "research": [
            {"id": r.id, "title": r.title, "research_area": r.research_area, "technologies": r.technologies}
            for r in ctx.research_items
        ],
        "verified_skills": sorted(name for name, ev in ctx.skill_index.items() if ev.verified),
    }


def generate_cv_plan(client, model: str, job: Job, ctx: ProfileContext) -> CVPlan:
    system_prompt = CV_PLAN_PROMPT_V1 + "\n\n---\n\n" + CV_PROJECT_SELECTION_PROMPT_V1
    payload = json.dumps({
        "job": {"title": job.title, "company": job.company, "requirements": _compact_requirements(job)},
        "profile": _compact_profile_for_planning(ctx),
    })
    output: CVPlanOutput = _call_structured(client, model, system_prompt, payload, CVPlanOutput)

    valid_experience_ids = {e.id for e in ctx.experiences}
    valid_project_ids = {p.id for p in ctx.projects}
    valid_research_ids = {r.id for r in ctx.research_items}
    valid_sections = {s.value for s in CVSectionType}

    return CVPlan(
        target_role=output.target_role or (job.title or "the target role"),
        priority_skills=[s for s in output.priority_skills if lookup_skill(ctx, s) is not None],
        selected_experience_ids=[i for i in output.selected_experience_ids if i in valid_experience_ids],
        selected_project_ids=[i for i in output.selected_project_ids if i in valid_project_ids],
        selected_research_ids=[i for i in output.selected_research_ids if i in valid_research_ids],
        sections=[CVSectionType(s) for s in output.sections if s in valid_sections],
        reasoning=output.reasoning,
    )


def _compact_selected_for_content(ctx: ProfileContext, plan: CVPlan) -> dict:
    experiences = [e for e in ctx.experiences if e.id in plan.selected_experience_ids]
    projects = [p for p in ctx.projects if p.id in plan.selected_project_ids]
    return {
        "priority_skills": plan.priority_skills,
        "verified_skills": sorted(name for name, ev in ctx.skill_index.items() if ev.verified),
        "experiences": [
            {
                "id": e.id, "company": e.company, "role": e.role, "technologies": e.technologies,
                "bullets": [{"id": b.id, "text": b.bullet, "skills": b.skills} for b in e.bullets],
            }
            for e in experiences
        ],
        "projects": [
            {
                "id": p.id, "name": p.name, "technologies": p.technologies,
                "results": [{"id": r.id, "description": r.description, "metric": r.metric} for r in p.results],
            }
            for p in projects
        ],
    }


def _validate_content(content: CVContentOutput, ctx: ProfileContext, job: Job, plan: CVPlan) -> tuple[list[ValidationIssue], dict]:
    issues: list[ValidationIssue] = []
    watch_terms = [r.skill_name or r.requirement_text for r in job.requirements] + plan.priority_skills

    skill_issues, sanitized_skills = validate_skill_categories(content, ctx)
    issues += skill_issues

    exp_by_id = {e.id: e for e in ctx.experiences}
    sanitized_experience: dict[int, list[dict]] = {}
    for exp_content in content.experience:
        exp = exp_by_id.get(exp_content.experience_id)
        if exp is None:
            issues.append(ValidationIssue(
                code="UNSUPPORTED_EXPERIENCE_SOURCE",
                message=f"Content references experience id {exp_content.experience_id}, which was not selected.",
                section="experience",
            ))
            continue
        valid_ids = {b.id for b in exp.bullets}
        original_by_id = {b.id: b.bullet for b in exp.bullets}
        known_tech_by_id = {b.id: set(b.skills) | set(exp.technologies) | set(exp.skills) for b in exp.bullets}
        bullet_issues, sanitized_bullets = validate_bullets(
            exp_content.bullets, valid_ids, original_by_id, known_tech_by_id, ctx, "experience", watch_terms
        )
        issues += bullet_issues
        sanitized_experience[exp.id] = sanitized_bullets

    proj_by_id = {p.id: p for p in ctx.projects}
    sanitized_projects: dict[int, list[dict]] = {}
    for proj_content in content.projects:
        proj = proj_by_id.get(proj_content.project_id)
        if proj is None:
            issues.append(ValidationIssue(
                code="UNSUPPORTED_PROJECT_SOURCE",
                message=f"Content references project id {proj_content.project_id}, which was not selected.",
                section="projects",
            ))
            continue
        valid_ids = {r.id for r in proj.results}
        # A ProjectResult's quantified achievement lives in `metric`,
        # separate from `description` (Step 1's design: "results stored
        # separately so a CV agent can choose relevant quantified
        # achievements"). A rewrite combining both is not introducing a
        # new number -- it's using the number that was always there.
        original_by_id = {r.id: f"{r.description} {r.metric or ''}".strip() for r in proj.results}
        known_tech_by_id = {r.id: set(proj.technologies) | set(proj.skills) for r in proj.results}
        bullet_issues, sanitized_bullets = validate_bullets(
            proj_content.bullets, valid_ids, original_by_id, known_tech_by_id, ctx, "projects", watch_terms
        )
        issues += bullet_issues
        sanitized_projects[proj.id] = sanitized_bullets

    issues += validate_summary(content.summary, ctx, watch_terms)

    return issues, {
        "skills": sanitized_skills,
        "experience": sanitized_experience,
        "projects": sanitized_projects,
    }


def generate_cv_content(client, model: str, job: Job, plan: CVPlan, ctx: ProfileContext) -> tuple[CVContentOutput, dict, list[ValidationIssue]]:
    system_prompt = CV_SUMMARY_PROMPT_V1 + "\n\n---\n\n" + CV_BULLET_REWRITE_PROMPT_V1 + "\n\n---\n\n" + CV_SKILL_SELECTION_PROMPT_V1
    payload = json.dumps({
        "job": {"title": job.title, "company": job.company, "target_role": plan.target_role},
        "selected_profile": _compact_selected_for_content(ctx, plan),
    })

    output = _call_structured(client, model, system_prompt, payload, CVContentOutput)
    issues, sanitized = _validate_content(output, ctx, job, plan)

    if issues:
        correction = (
            "The following items were rejected as unsupported by the career profile and must not "
            "appear in a corrected response: " + "; ".join(i.message for i in issues) +
            ". Regenerate using only the given profile data, referencing only the given bullet/result ids."
        )
        output = _call_structured(client, model, system_prompt, payload + "\n\nCORRECTION:\n" + correction, CVContentOutput)
        issues, sanitized = _validate_content(output, ctx, job, plan)

    return output, sanitized, issues


def _cv_header(ctx: ProfileContext) -> CVHeader:
    profile = ctx.profile
    location = ", ".join(filter(None, [profile.city, profile.country])) or None
    return CVHeader(
        name=profile.full_name,
        email=profile.email,
        phone=profile.phone,
        linkedin=profile.linkedin_url,
        github=profile.github_url,
        portfolio=profile.portfolio_url,
        location=location,
    )


def assemble_cv_content(job: Job, plan: CVPlan, content: CVContentOutput, sanitized: dict, ctx: ProfileContext) -> CVContent:
    exp_by_id = {e.id: e for e in ctx.experiences}
    proj_by_id = {p.id: p for p in ctx.projects}
    bullet_verified_by_id = {b.id: b.verified for e in ctx.experiences for b in e.bullets}
    result_verified_by_id = {r.id: r.verified for p in ctx.projects for r in p.results}

    experience_entries = []
    for exp_id in plan.selected_experience_ids:
        exp = exp_by_id.get(exp_id)
        bullets = sanitized["experience"].get(exp_id, [])
        if exp is None or not bullets:
            continue
        experience_entries.append(CVExperienceEntry(
            experience_id=exp.id, company=exp.company, role=exp.role, location=exp.location,
            start_date=exp.start_date, end_date=exp.end_date, currently_working=exp.currently_working,
            bullets=[
                CVBullet(
                    text=b["text"], source_type=EntityType.EXPERIENCE_BULLET, source_id=b["source_bullet_id"],
                    verified=bullet_verified_by_id.get(b["source_bullet_id"], False),
                )
                for b in bullets
            ],
        ))

    project_entries = []
    for proj_id in plan.selected_project_ids:
        proj = proj_by_id.get(proj_id)
        bullets = sanitized["projects"].get(proj_id, [])
        if proj is None:
            continue
        project_entries.append(CVProjectEntry(
            project_id=proj.id, name=proj.name, technologies=proj.technologies, github_url=proj.github_url,
            bullets=[
                CVBullet(
                    text=b["text"], source_type=EntityType.PROJECT_RESULT, source_id=b["source_bullet_id"],
                    verified=result_verified_by_id.get(b["source_bullet_id"], False),
                )
                for b in bullets
            ],
        ))

    research_entries = [
        CVResearchEntry(
            research_id=r.id, title=r.title, research_area=r.research_area,
            technologies=r.technologies, description=r.description,
        )
        for r in ctx.research_items if r.id in plan.selected_research_ids
    ]

    education_entries = [
        CVEducationEntry(
            education_id=e.id, institution=e.institution, degree=e.degree, field=e.field,
            start_date=e.start_date, end_date=e.end_date, grade=e.grade,
        )
        for e in ctx.educations
    ] if CVSectionType.EDUCATION in plan.sections else []

    certification_entries = [
        CVCertificationEntry(certification_id=c.id, name=c.name, issuer=c.issuer, issue_date=c.issue_date)
        for c in ctx.certifications
    ] if CVSectionType.CERTIFICATIONS in plan.sections else []

    achievement_entries = [
        CVAchievementEntry(achievement_id=a.id, title=a.title, description=a.description, metric=a.metric)
        for a in ctx.achievements
    ] if CVSectionType.ACHIEVEMENTS in plan.sections else []

    return CVContent(
        header=_cv_header(ctx),
        summary=content.summary,
        skills=[CVSkillCategory(category=c["category"], skills=c["skills"]) for c in sanitized["skills"]],
        experience=experience_entries,
        projects=project_entries,
        research=research_entries,
        education=education_entries,
        certifications=certification_entries,
        achievements=achievement_entries,
        section_order=plan.sections,
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
    """The full Step 3 pipeline: JOB -> JOB MATCH -> CAREER PROFILE ->
    select relevant evidence -> CV plan -> CV content -> validate -> reject
    unsupported claims -> LaTeX -> PDF -> store CV version."""

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
    output, sanitized, issues = generate_cv_content(client, model, job, plan, ctx)

    summary_has_unsupported_claim = any(i.code == "UNSUPPORTED_TECHNOLOGY_IN_SUMMARY" for i in issues)
    final_summary = _fallback_summary(plan, ctx) if summary_has_unsupported_claim else output.summary
    sanitized["summary"] = final_summary

    content = assemble_cv_content(job, plan, output.model_copy(update={"summary": final_summary}), sanitized, ctx)

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
