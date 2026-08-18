"""Step 7 interview-prep wrappers that go beyond the read-only context
already covered by application.get_interview_preparation (see
application.py) -- these two call the local Ollama model to generate
draft questions/answers, grounded only in the real job description and
verified Career Profile (never invented, per Steps 4/7's existing
validation)."""

from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.agent.tool_registry import ToolSpec, register
from app.agent.tools._util import call_router
from app.api.intelligence import generate_interview_answer, generate_interview_questions
from app.models.enums import ToolPermission, ToolRiskLevel
from app.schemas.intelligence import InterviewAnswerRequest, InterviewQuestionsRequest


class InterviewQuestionsArgs(BaseModel):
    application_id: int
    categories: list[str] | None = None


async def interview_generate_questions(db: Session, args: InterviewQuestionsArgs) -> dict:
    payload = InterviewQuestionsRequest(application_id=args.application_id, categories=args.categories)
    result, error = await call_router(generate_interview_questions, payload=payload, db=db)
    if error:
        return {"success": False, "errors": [error]}
    return result.model_dump(mode="json")


class InterviewAnswerArgs(BaseModel):
    application_id: int
    question: str
    star: bool = False


async def interview_generate_answer(db: Session, args: InterviewAnswerArgs) -> dict:
    payload = InterviewAnswerRequest(application_id=args.application_id, question=args.question, star=args.star)
    result, error = await call_router(generate_interview_answer, payload=payload, db=db)
    if error:
        return {"success": False, "errors": [error]}
    return result.model_dump(mode="json")


register(ToolSpec(
    name="interview.generate_questions", description="Generate likely interview questions for an application (local Ollama, grounded in the real job description).",
    input_schema=InterviewQuestionsArgs, permission=ToolPermission.READ_ONLY, risk=ToolRiskLevel.LOW, handler=interview_generate_questions,
))
register(ToolSpec(
    name="interview.generate_answer", description="Draft a STAR-format answer to an interview question, grounded only in the verified Career Profile.",
    input_schema=InterviewAnswerArgs, permission=ToolPermission.READ_ONLY, risk=ToolRiskLevel.LOW, handler=interview_generate_answer,
))
