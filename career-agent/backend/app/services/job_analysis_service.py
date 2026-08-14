"""AI-powered extraction of structured requirements from a job's cleaned
description. Exactly one LLM call per analysis, validated against
JobAnalysisResult -- never trusted as free-form text.
"""

import logging
import re
from datetime import datetime, timezone

from pydantic import ValidationError
from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.ai.client import get_openai_client
from app.ai.prompts import JOB_ANALYSIS_PROMPT_V1
from app.ai.structured_outputs import JobAnalysisResult
from app.config import get_settings
from app.models.enums import JobStatus, RequirementCategory, RequirementImportance
from app.models.job import Job
from app.models.job_requirement import JobRequirement
from app.services.job_ingestion_service import find_possible_duplicate_by_identity

logger = logging.getLogger("app.job_analysis")

CRITICAL_KEYWORDS = (
    "must have", "must possess", "required to have", "mandatory",
    "active clearance", "security clearance", "active security clearance",
)

YEARS_PATTERN = re.compile(r"(\d+(?:\.\d+)?)\+?\s*(?:-\s*\d+(?:\.\d+)?\s*)?years?", re.IGNORECASE)
PREFERRED_LANGUAGE_PATTERN = re.compile(r"\b(preferred|nice to have|a plus|bonus|desirable)\b", re.IGNORECASE)


class AnalysisInputError(ValueError):
    pass


class AIResponseError(RuntimeError):
    """The LLM returned something that didn't validate as JobAnalysisResult."""


def _extract_years_required(text: str) -> float | None:
    match = YEARS_PATTERN.search(text)
    if not match:
        return None
    try:
        return float(match.group(1))
    except ValueError:
        return None


def _looks_critical(text: str) -> bool:
    lowered = text.lower()
    return any(keyword in lowered for keyword in CRITICAL_KEYWORDS)


def _looks_preferred_language(text: str) -> bool:
    return bool(PREFERRED_LANGUAGE_PATTERN.search(text))


def call_job_analysis(client, model: str, description: str) -> JobAnalysisResult:
    try:
        completion = client.chat.completions.parse(
            model=model,
            messages=[
                {"role": "system", "content": JOB_ANALYSIS_PROMPT_V1},
                {"role": "user", "content": description},
            ],
            response_format=JobAnalysisResult,
        )
    except Exception as exc:
        logger.error("openai job analysis call failed: %s", exc.__class__.__name__)
        raise AIResponseError(f"OpenAI request failed: {exc}") from exc

    parsed = completion.choices[0].message.parsed
    if parsed is None:
        refusal = getattr(completion.choices[0].message, "refusal", None)
        raise AIResponseError(f"Model did not return structured output: {refusal or 'unknown reason'}")

    try:
        return JobAnalysisResult.model_validate(parsed.model_dump())
    except ValidationError as exc:
        raise AIResponseError(f"AI response failed schema validation: {exc}") from exc


def _build_requirements(job_id: int, result: JobAnalysisResult) -> list[JobRequirement]:
    requirements: list[JobRequirement] = []

    def add(text: str, category: RequirementCategory, required: bool, **kwargs):
        text = text.strip()
        if not text:
            return
        importance = RequirementImportance.CRITICAL if (required and _looks_critical(text)) else kwargs.pop(
            "importance", RequirementImportance.HIGH if required else RequirementImportance.MEDIUM
        )
        requirements.append(
            JobRequirement(
                job_id=job_id,
                requirement_text=text,
                category=category,
                importance=importance,
                required=required,
                skill_name=kwargs.get("skill_name"),
                years_required=kwargs.get("years_required"),
                education_requirement=kwargs.get("education_requirement"),
                evidence_required=kwargs.get("evidence_required", True),
            )
        )

    for skill in result.required_skills:
        add(skill, RequirementCategory.TECHNICAL_SKILL, required=True, skill_name=skill.strip())

    for skill in result.preferred_skills:
        add(skill, RequirementCategory.TECHNICAL_SKILL, required=False, skill_name=skill.strip())

    for exp in result.required_experience:
        add(exp, RequirementCategory.EXPERIENCE, required=True, years_required=_extract_years_required(exp))

    for exp in result.preferred_experience:
        add(exp, RequirementCategory.EXPERIENCE, required=False, years_required=_extract_years_required(exp))

    for edu in result.education_requirements:
        required = not _looks_preferred_language(edu)
        add(edu, RequirementCategory.EDUCATION, required=required, education_requirement=edu.strip())

    for resp in result.responsibilities:
        add(resp, RequirementCategory.RESPONSIBILITY, required=True, importance=RequirementImportance.MEDIUM)

    for cert in result.certifications:
        required = not _looks_preferred_language(cert)
        add(cert, RequirementCategory.CERTIFICATION, required=required)

    for loc in result.location_requirements:
        add(loc, RequirementCategory.LOCATION, required=True, importance=RequirementImportance.MEDIUM)

    for auth in result.work_authorization_requirements:
        add(auth, RequirementCategory.WORK_AUTHORIZATION, required=True, importance=RequirementImportance.CRITICAL)

    return requirements


def analyze_job(db: Session, job: Job) -> Job:
    if not job.description:
        raise AnalysisInputError(
            "This job has no description to analyze. Provide a description, or a URL that "
            "could be fetched, before requesting analysis."
        )

    settings = get_settings()
    client = get_openai_client()
    result = call_job_analysis(client, settings.openai_model, job.description)

    if not job.title and result.job_title:
        job.title = result.job_title.strip()
    if not job.company and result.company:
        job.company = result.company.strip()
    if not job.location and result.location:
        job.location = result.location.strip()

    job.summary = result.job_summary.strip()
    job.keywords = [k.strip() for k in result.keywords if k.strip()]
    job.extracted_at = datetime.now(timezone.utc)
    job.status = JobStatus.ANALYZED

    db.execute(delete(JobRequirement).where(JobRequirement.job_id == job.id))
    db.flush()
    requirements = _build_requirements(job.id, result)
    db.add_all(requirements)

    duplicate = find_possible_duplicate_by_identity(db, job)
    if duplicate:
        job.duplicate_of_job_id = duplicate.id
        logger.info("job id=%s flagged as possible duplicate of id=%s", job.id, duplicate.id)

    db.commit()
    db.refresh(job)
    logger.info("job id=%s analyzed, %d requirements extracted", job.id, len(requirements))
    return job
