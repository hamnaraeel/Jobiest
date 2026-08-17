"""Interview intelligence (spec sections 27-31): preparation context and
output, question generation, and draft-answer assistance -- the only
place in Step 7 that calls the local LLM for generation rather than
explanation (recommendation_explainer.py handles the explanation side).

Question generation never claims certainty about what a specific
interviewer will ask (enforced by prompt wording AND a disclaimer this
module always attaches, regardless of what the model returns). Answer
generation reuses Step 4's exact hallucination-check validator
(`answer_validation_service.validate_generated_text`) -- the same
"never invent a skill/metric/company claim" rule that already governs
cover letters and application answers.
"""

import logging
from collections import Counter
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.ai.client import OllamaClient
from app.ai.interview_prep_outputs import InterviewAnswerOutput, InterviewQuestionsOutput
from app.ai.interview_prep_prompts import INTERVIEW_ANSWER_PROMPT_V1, INTERVIEW_QUESTIONS_PROMPT_V1
from app.models.application import Application
from app.models.enums import RequirementCategory, RequirementImportance
from app.services import tracking_service
from app.services.answer_validation_service import validate_generated_text
from app.services.job_matching_service import ProfileContext, get_relevant_career_data

logger = logging.getLogger("app.intelligence.interview_analyzer")

QUESTION_CATEGORIES = ("technical", "behavioral", "project", "system_design", "role_specific")


class InterviewPrepInputError(ValueError):
    pass


@dataclass
class InterviewPrepOutput:
    role: str | None
    company: str | None
    top_technical_areas: list[str] = field(default_factory=list)
    strongest_matching_projects: list[str] = field(default_factory=list)
    potential_weak_areas: list[str] = field(default_factory=list)
    likely_question_areas: list[str] = field(default_factory=list)


def build_preparation_output(db: Session, application: Application) -> InterviewPrepOutput:
    """The formatted "INTERVIEW PREPARATION" view (spec section 28) --
    a deterministic re-ranking of tracking_service.build_interview_context(),
    not a new data source."""

    context = tracking_service.build_interview_context(db, application)

    job = application.job
    requirements = []
    if job is not None:
        requirements = [r for r in job.requirements if r.category == RequirementCategory.TECHNICAL_SKILL]
    importance_rank = {RequirementImportance.CRITICAL: 3, RequirementImportance.HIGH: 2, RequirementImportance.MEDIUM: 1, RequirementImportance.LOW: 0}
    ranked = sorted(requirements, key=lambda r: importance_rank.get(r.importance, 0), reverse=True)
    top_technical_areas = [(r.skill_name or r.requirement_text) for r in ranked[:5]]

    matched = set(context["matched_skills"])
    weak_areas = [area for area in context["required_skills"] if area not in matched][:5]

    likely_question_areas = list(top_technical_areas[:2])
    if context["projects_used"]:
        likely_question_areas.append("Project discussion")
    likely_question_areas.append("Deployment / production considerations")
    if weak_areas:
        likely_question_areas.append(f"Areas outside your matched skills (e.g. {weak_areas[0]})")

    return InterviewPrepOutput(
        role=context["job_title"], company=context["company"],
        top_technical_areas=top_technical_areas,
        strongest_matching_projects=context["projects_used"],
        potential_weak_areas=weak_areas,
        likely_question_areas=likely_question_areas,
    )


def generate_questions(
    client: OllamaClient, model: str, application: Application, categories: list[str] | None = None,
) -> list[dict]:
    """POST /interview-prep/questions (spec sections 29-30). Returns
    plain dicts (not persisted) -- the caller decides what to do with them."""

    job = application.job
    if job is None:
        raise InterviewPrepInputError("This application has no associated job.")

    categories = categories or list(QUESTION_CATEGORIES)
    required_skills = [
        r.skill_name or r.requirement_text for r in job.requirements
        if r.category == RequirementCategory.TECHNICAL_SKILL
    ]
    cv_summary = application.cv_version.summary if application.cv_version else None

    payload = (
        f"Job title: {job.title}\nCompany: {job.company}\n"
        f"Job description:\n{job.description or '(not provided)'}\n\n"
        f"Required skills: {', '.join(required_skills) or '(none extracted)'}\n"
        f"Candidate CV summary: {cv_summary or '(not available)'}\n\n"
        f"Generate questions covering these categories: {', '.join(categories)}."
    )

    output: InterviewQuestionsOutput = client.chat_structured(INTERVIEW_QUESTIONS_PROMPT_V1, payload, InterviewQuestionsOutput)
    questions = [
        {"question": q.question, "category": q.category if q.category in QUESTION_CATEGORIES else "role_specific"}
        for q in output.questions
    ]
    return questions


def generate_answer(
    db: Session, client: OllamaClient, application: Application, question: str, profile_id: int, star: bool = False,
) -> dict:
    """POST /interview-prep/answer (spec sections 30-31). Grounded only
    in the candidate's own verified evidence; validated with the same
    hallucination check Step 4 uses for application answers."""

    ctx: ProfileContext = get_relevant_career_data(db, profile_id)
    job = application.job

    prompt_payload = (
        f"Interview question: {question}\n\n"
        f"Job title: {job.title if job else '(unknown)'}\nCompany: {job.company if job else '(unknown)'}\n"
        f"Candidate's verified skills: {', '.join(ctx.skill_index.keys())}\n"
        f"Candidate's experience: {'; '.join(f'{e.role} at {e.company}' for e in ctx.experiences)}\n"
        f"Candidate's projects: {', '.join(p.name for p in ctx.projects)}\n"
    )
    if star:
        prompt_payload += "\nStructure the answer using STAR (Situation, Task, Action, Result)."

    output: InterviewAnswerOutput = client.chat_structured(INTERVIEW_ANSWER_PROMPT_V1, prompt_payload, InterviewAnswerOutput)

    watch_terms = [r.skill_name or r.requirement_text for r in job.requirements] if job else []
    issues = validate_generated_text(output.answer, ctx, watch_terms, job_description=(job.description if job else "") or "")

    result = {
        "answer": output.answer,
        "star": {"situation": output.situation, "task": output.task, "action": output.action, "result": output.result} if star else None,
        "validation_issues": [issue.message for issue in issues],
        "validated": not issues,
    }
    if issues:
        logger.warning("interview answer failed validation for application_id=%s: %s", application.id, [i.code for i in issues])
    return result
