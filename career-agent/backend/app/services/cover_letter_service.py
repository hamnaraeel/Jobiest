"""Orchestrates cover letter generation: retrieve evidence deterministically
(no extra LLM call for this -- reuses the same skill-overlap idea as
Step 3's CV plan) -> generate one structured letter via Ollama -> validate
deterministically -> retry once with corrections if unsupported claims
survive -> store a new version. Requires an APPROVED CV, per the Step 4
workflow: JOB -> JOB MATCH -> APPROVED CV -> CAREER PROFILE -> ... .
"""

import json
import logging
import re
from datetime import date as date_cls
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai.client import call_ollama_structured, get_ollama_client
from app.ai.cover_letter_prompts import COVER_LETTER_PROMPT_V1, COVER_LETTER_REGENERATE_INSTRUCTIONS_PREFIX
from app.ai.structured_outputs import CoverLetterOutput
from app.config import get_settings
from app.models.cover_letter import CoverLetter
from app.models.cv_version import CVVersion
from app.models.enums import ApplicationMaterialStatus, CVStatus, EntityType
from app.models.job import Job
from app.schemas.cover_letter import ALLOWED_LENGTHS, ALLOWED_STYLES
from app.services import cv_render_service
from app.services.answer_validation_service import validate_generated_text
from app.services.job_matching_service import ProfileContext, get_relevant_career_data, lookup_skill, skills_equivalent
from app.services.profile_service import get_default_profile

logger = logging.getLogger("app.cover_letter")

_ADD_INSTRUCTION_PATTERN = re.compile(
    r"\b(?:add|mention|include|emphasize|highlight)\s+([A-Za-z][A-Za-z0-9+.#/ ]{0,40}?)\s*(?:to|in|on|within|$|[.,])",
    re.IGNORECASE,
)


class CoverLetterInputError(ValueError):
    pass


class CoverLetterStyleError(ValueError):
    pass


def _check_instructions_for_unsupported_additions(instructions: str | None, ctx: ProfileContext) -> None:
    """Spec example: user says 'Add AWS to my cover letter' and AWS isn't
    verified -> reject the request outright, before ever calling the LLM,
    with the exact reason the spec asks for. The prompt also tells the
    model to ignore such instructions, but this catches it deterministically
    up front rather than hoping the model (and the post-hoc validator)
    both behave."""

    if not instructions:
        return
    for match in _ADD_INSTRUCTION_PATTERN.finditer(instructions):
        term = match.group(1).strip().rstrip(".,")
        if term and lookup_skill(ctx, term) is None:
            raise CoverLetterInputError(f"{term} is not present in the verified Career Profile.")


def select_relevant_evidence(ctx: ProfileContext, job: Job, limit_each: int = 3):
    """No extra LLM call: rank experience/project/research items by how
    many of the job's required+preferred skill names they demonstrate,
    same idea as Step 3's CV plan without the planning call."""

    job_terms = [r.skill_name or r.requirement_text for r in job.requirements]

    def score(technologies, skills):
        names = set(technologies) | set(skills)
        return sum(1 for term in job_terms if any(skills_equivalent(term, name) for name in names))

    def top(items, key_fn):
        ranked = sorted(items, key=key_fn, reverse=True)
        relevant = [i for i in ranked if key_fn(i) > 0][:limit_each]
        return relevant if relevant else ranked[:limit_each]

    experiences = top(ctx.experiences, lambda e: score(e.technologies, e.skills))
    projects = top(ctx.projects, lambda p: score(p.technologies, p.skills))
    research = top(ctx.research_items, lambda r: score(r.technologies, []))
    return experiences, projects, research


def evidence_refs(experiences, projects, research) -> list[dict]:
    refs = [{"source_type": EntityType.EXPERIENCE.value, "source_id": e.id} for e in experiences]
    refs += [{"source_type": EntityType.PROJECT.value, "source_id": p.id} for p in projects]
    refs += [{"source_type": EntityType.RESEARCH.value, "source_id": r.id} for r in research]
    return refs


def _compact_evidence(profile, job: Job, experiences, projects, research, ctx: ProfileContext, word_target: tuple[int, int]) -> dict:
    return {
        "job": {
            "title": job.title,
            "company": job.company,
            "requirements": [
                {"text": r.requirement_text, "required": r.required, "skill_name": r.skill_name}
                for r in job.requirements
            ],
        },
        "candidate": {
            "name": profile.full_name,
            "title": profile.professional_title,
            "verified_skills": sorted(name for name, ev in ctx.skill_index.items() if ev.verified),
        },
        "experience": [
            {"company": e.company, "role": e.role, "technologies": e.technologies, "bullets": [b.bullet for b in e.bullets]}
            for e in experiences
        ],
        "projects": [
            {"name": p.name, "technologies": p.technologies,
             "results": [f"{r.description} {r.metric or ''}".strip() for r in p.results]}
            for p in projects
        ],
        "research": [
            {"title": r.title, "technologies": r.technologies, "results": r.results}
            for r in research
        ],
        "target_word_count": {"min": word_target[0], "max": word_target[1]},
    }


def _word_target(length: str | None) -> tuple[int, int]:
    settings = get_settings()
    lo, hi = settings.cover_letter_min_words, settings.cover_letter_max_words
    mid = (lo + hi) // 2
    return {
        None: (lo, hi),
        "medium": (lo, hi),
        "short": (lo, mid),
        "long": (mid, hi + 100),
    }[length]


def _build_system_prompt(style: str | None, instructions: str | None) -> str:
    prompt = COVER_LETTER_PROMPT_V1
    if style:
        prompt += f"\n\nWriting style requested: {style}."
    if instructions:
        prompt += "\n\n" + COVER_LETTER_REGENERATE_INSTRUCTIONS_PREFIX + instructions
    return prompt


def generate_cover_letter(
    db: Session,
    job: Job,
    cv_version: CVVersion,
    style: str | None = None,
    length: str | None = None,
    focus: list[str] | None = None,
    instructions: str | None = None,
) -> CoverLetter:
    if style is not None and style not in ALLOWED_STYLES:
        raise CoverLetterStyleError(f"Invalid style '{style}'. Allowed: {', '.join(ALLOWED_STYLES)}")
    if length is not None and length not in ALLOWED_LENGTHS:
        raise CoverLetterStyleError(f"Invalid length '{length}'. Allowed: {', '.join(ALLOWED_LENGTHS)}")

    if cv_version.status != CVStatus.APPROVED:
        raise CoverLetterInputError(
            f"Cover letter generation requires an approved CV (current status: "
            f"'{cv_version.status.value}'). Approve a CV version first via PATCH /cvs/{{id}}/status."
        )
    if not job.requirements:
        raise CoverLetterInputError("This job has no extracted requirements yet -- analyze it first.")

    profile = get_default_profile(db)
    if profile is None:
        raise CoverLetterInputError("No career profile exists yet.")

    ctx = get_relevant_career_data(db, profile.id)
    _check_instructions_for_unsupported_additions(instructions, ctx)

    experiences, projects, research = select_relevant_evidence(ctx, job)
    if focus:
        # Focus areas bias which items are prioritized in the prompt, but
        # never add anything not already selected by relevance scoring --
        # focus can't smuggle in unsupported evidence.
        experiences = sorted(experiences, key=lambda e: any(skills_equivalent(f, s) for f in focus for s in e.skills), reverse=True)
        projects = sorted(projects, key=lambda p: any(skills_equivalent(f, s) for f in focus for s in p.skills), reverse=True)

    word_target = _word_target(length)
    system_prompt = _build_system_prompt(style, instructions)
    payload_dict = _compact_evidence(profile, job, experiences, projects, research, ctx, word_target)
    payload = json.dumps(payload_dict)

    client = get_ollama_client()
    settings = get_settings()
    watch_terms = [r.skill_name or r.requirement_text for r in job.requirements]

    output = call_ollama_structured(client, system_prompt, payload, CoverLetterOutput)
    issues = validate_generated_text(output.full_text, ctx, watch_terms, job_description=job.description or "")

    if issues:
        correction = (
            "The following issues were found in your previous draft and must not appear in a "
            "corrected version: " + "; ".join(i.message for i in issues) + ". Regenerate the full "
            "letter using only the given evidence."
        )
        output = call_ollama_structured(client, system_prompt, payload + "\n\nCORRECTION:\n" + correction, CoverLetterOutput)
        issues = validate_generated_text(output.full_text, ctx, watch_terms, job_description=job.description or "")

    word_count = len(output.full_text.split())
    word_count_ok = word_target[0] <= word_count <= word_target[1] + 100  # soft ceiling; never truncated mechanically

    version_number = db.execute(
        select(func.count(CoverLetter.id)).where(CoverLetter.job_id == job.id)
    ).scalar_one() + 1
    version_name = f"{job.title or 'Role'} - {job.company or 'Company'} - V{version_number}"

    warnings = [issue.message for issue in issues]
    if not word_count_ok:
        warnings.append(f"Word count {word_count} is outside the target range {word_target[0]}-{word_target[1]}.")

    status = ApplicationMaterialStatus.REJECTED if issues else (
        ApplicationMaterialStatus.DRAFT if not word_count_ok else ApplicationMaterialStatus.VALIDATED
    )

    cover_letter = CoverLetter(
        job_id=job.id, cv_version_id=cv_version.id, profile_id=profile.id,
        version_name=version_name, version_number=version_number,
        title=f"Cover Letter - {job.title or 'Role'} at {job.company or 'Company'}",
        content=output.full_text, word_count=word_count, status=status,
        source_evidence=evidence_refs(experiences, projects, research),
        warnings=warnings,
    )
    db.add(cover_letter)
    db.commit()
    db.refresh(cover_letter)

    logger.info(
        "cover letter generated job_id=%s version=%d status=%s words=%d",
        job.id, version_number, status.value, word_count,
    )
    return cover_letter


def ensure_cover_letter_pdf(db: Session, cover_letter: CoverLetter) -> str:
    """Compiled lazily on first PDF download request, not at generation
    time -- many users only ever want the .txt, so there's no reason to
    spend a pdflatex run on every generated version."""

    if cover_letter.pdf_path and Path(cover_letter.pdf_path).exists():
        return cover_letter.pdf_path

    profile = cover_letter.profile
    contact_parts = [profile.email, profile.phone, profile.linkedin_url, profile.github_url]
    latex_source = cv_render_service.render_cover_letter_to_latex(
        name=profile.full_name,
        contact_parts=contact_parts,
        date_str=date_cls.today().strftime("%B %d, %Y"),
        company=cover_letter.job.company or "",
        body_text=cover_letter.content,
    )
    result = cv_render_service.compile_cover_letter_pdf(latex_source, cover_letter.job_id, cover_letter.version_number)
    if not result.success:
        raise CoverLetterInputError(f"PDF compilation failed: {result.error}")

    cover_letter.pdf_path = result.pdf_path
    db.commit()
    db.refresh(cover_letter)
    return cover_letter.pdf_path
