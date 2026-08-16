"""Classifies application questions, generates answers via Ollama with
deterministic length enforcement, and handles the "never guess" special
cases (salary/authorization/relocation/availability) explicitly rather
than letting the LLM improvise.
"""

import json
import logging

from sqlalchemy.orm import Session

from app.ai.application_prompts import APPLICATION_ANSWER_PROMPT_V1, APPLICATION_ANSWER_SHORTEN_PROMPT_V1
from app.ai.client import OllamaResponseError, call_ollama_structured, get_ollama_client
from app.ai.structured_outputs import ApplicationAnswerOutput
from app.models.application_answer import ApplicationAnswer
from app.models.application_question import ApplicationQuestion
from app.models.enums import ApplicationMaterialStatus, ApplicationQuestionType
from app.models.job import Job
from app.services.answer_validation_service import validate_generated_text
from app.services.cover_letter_service import evidence_refs, select_relevant_evidence
from app.services.job_matching_service import get_relevant_career_data
from app.services.profile_service import get_default_profile

logger = logging.getLogger("app.application_answer")

MAX_SHORTEN_ATTEMPTS = 2

_TYPE_KEYWORDS: list[tuple[ApplicationQuestionType, tuple[str, ...]]] = [
    (ApplicationQuestionType.SALARY, ("salary", "compensation", "pay expectation", "expected pay", "desired pay")),
    (ApplicationQuestionType.AUTHORIZATION, ("authorized to work", "work authorization", "visa", "sponsorship", "eligible to work", "legally work")),
    (ApplicationQuestionType.RELOCATION, ("relocate", "relocation", "willing to move")),
    (ApplicationQuestionType.AVAILABILITY, ("available to start", "start date", "notice period", "when can you start", "your availability")),
    (ApplicationQuestionType.COMPANY, ("work for this company", "work for us", "work here", "join our company", "why our company", "why this company")),
    (ApplicationQuestionType.MOTIVATION, ("why are you interested", "why this role", "why this position", "why should we hire")),
    (ApplicationQuestionType.BEHAVIORAL, ("challenging project", "describe a time", "a challenge", "proud of", "biggest strength", "your strengths", "your weakness")),
    (ApplicationQuestionType.TECHNICAL, ("experience with", "describe your experience", "technical skills", "your experience in")),
    (ApplicationQuestionType.GENERAL, ("tell us about yourself", "tell me about yourself", "career goals", "looking for a new opportunity")),
]


class AnswerInputError(ValueError):
    pass


class ManualInputRequiredError(Exception):
    """Raised for question types the profile has no verified preference
    for. Never guessed, never randomly generated -- see spec sections
    24-27 (salary/authorization/relocation/availability)."""

    def __init__(self, question_type: ApplicationQuestionType, reason: str):
        self.question_type = question_type
        self.reason = reason
        super().__init__(reason)


def classify_question_type(question_text: str) -> ApplicationQuestionType:
    lowered = question_text.lower()
    for qtype, keywords in _TYPE_KEYWORDS:
        if any(kw in lowered for kw in keywords):
            return qtype
    return ApplicationQuestionType.UNKNOWN


def _check_manual_input_required(question_type: ApplicationQuestionType, profile) -> str | None:
    if question_type == ApplicationQuestionType.SALARY and not profile.salary_expectation:
        return "No salary expectation is configured on the career profile."
    if question_type == ApplicationQuestionType.AUTHORIZATION and not profile.work_authorization:
        return "No work authorization information is configured on the career profile."
    if question_type == ApplicationQuestionType.RELOCATION and not profile.relocation_preference:
        return "No relocation preference is configured on the career profile."
    if question_type == ApplicationQuestionType.AVAILABILITY and not profile.availability_date:
        return "No availability date is configured on the career profile."
    return None


def _limit_note(question: ApplicationQuestion) -> str:
    parts = []
    if question.character_limit:
        parts.append(f"maximum {question.character_limit} characters")
    if question.word_limit:
        parts.append(f"maximum {question.word_limit} words")
    return "; ".join(parts) if parts else "no strict limit, but be concise (typically well under 150 words)"


def _exceeds_limit(text: str, question: ApplicationQuestion) -> bool:
    if question.character_limit and len(text) > question.character_limit:
        return True
    if question.word_limit and len(text.split()) > question.word_limit:
        return True
    return False


def _shorten_until_fits(client, text: str, question: ApplicationQuestion) -> tuple[str, str | None]:
    """Up to MAX_SHORTEN_ATTEMPTS LLM-assisted shortenings, each
    re-validated in Python -- never a mechanical string truncation, since
    that can cut a claim mid-sentence in a misleading way."""

    if not _exceeds_limit(text, question):
        return text, None

    current = text
    for attempt in range(MAX_SHORTEN_ATTEMPTS):
        payload = json.dumps({"text": current, "limit": _limit_note(question)})
        try:
            shortened = call_ollama_structured(client, APPLICATION_ANSWER_SHORTEN_PROMPT_V1, payload, ApplicationAnswerOutput, max_retries=0)
        except OllamaResponseError as exc:
            logger.warning("shortening attempt %d failed: %s", attempt + 1, exc)
            break
        current = shortened.answer
        if not _exceeds_limit(current, question):
            return current, None

    return current, "Unable to fit within character/word limit without risking loss of important information."


def generate_answer(db: Session, question: ApplicationQuestion, job: Job) -> ApplicationAnswer:
    profile = get_default_profile(db)
    if profile is None:
        raise AnswerInputError("No career profile exists yet.")
    if not job.requirements:
        raise AnswerInputError("This job has no extracted requirements yet -- analyze it first.")

    if question.question_type == ApplicationQuestionType.UNKNOWN:
        question.question_type = classify_question_type(question.question)
        db.commit()
        db.refresh(question)

    manual_reason = _check_manual_input_required(question.question_type, profile)
    if manual_reason:
        raise ManualInputRequiredError(question.question_type, manual_reason)

    ctx = get_relevant_career_data(db, profile.id)
    experiences, projects, research = select_relevant_evidence(ctx, job)

    payload = json.dumps({
        "question": question.question,
        "question_type": question.question_type.value,
        "job": {"title": job.title, "company": job.company},
        "candidate": {
            "name": profile.full_name, "title": profile.professional_title,
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
        "research": [{"title": r.title, "technologies": r.technologies, "results": r.results} for r in research],
        "length_limit": _limit_note(question),
    })

    client = get_ollama_client()
    watch_terms = [r.skill_name or r.requirement_text for r in job.requirements]

    output = call_ollama_structured(client, APPLICATION_ANSWER_PROMPT_V1, payload, ApplicationAnswerOutput)
    issues = validate_generated_text(output.answer, ctx, watch_terms, job_description=job.description or "")

    if issues:
        correction = (
            "The following issues were found and must not appear in a corrected version: "
            + "; ".join(i.message for i in issues) + ". Regenerate using only the given evidence."
        )
        output = call_ollama_structured(client, APPLICATION_ANSWER_PROMPT_V1, payload + "\n\nCORRECTION:\n" + correction, ApplicationAnswerOutput)
        issues = validate_generated_text(output.answer, ctx, watch_terms, job_description=job.description or "")

    answer_text, length_issue = _shorten_until_fits(client, output.answer, question)

    warnings = [i.message for i in issues]
    if length_issue:
        warnings.append(length_issue)

    status = ApplicationMaterialStatus.REJECTED if issues else (
        ApplicationMaterialStatus.DRAFT if length_issue else ApplicationMaterialStatus.VALIDATED
    )

    answer = ApplicationAnswer(
        question_id=question.id, answer=answer_text,
        word_count=len(answer_text.split()), character_count=len(answer_text),
        status=status, evidence=evidence_refs(experiences, projects, research), warnings=warnings,
    )
    db.add(answer)
    db.commit()
    db.refresh(answer)

    logger.info("answer generated question_id=%s status=%s chars=%d", question.id, status.value, len(answer_text))
    return answer
