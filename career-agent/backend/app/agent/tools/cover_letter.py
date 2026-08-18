"""Step 4 wrappers: cover letter generation/approval."""

from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.agent.tool_registry import ToolSpec, register
from app.agent.tools._util import call_router
from app.api.applications import generate_job_cover_letter, update_cover_letter_status
from app.models.enums import ApplicationMaterialStatus, ToolPermission, ToolRiskLevel
from app.schemas.cover_letter import CoverLetterGenerateRequest, CoverLetterStatusUpdateRequest


class CoverLetterGenerateArgs(BaseModel):
    job_id: int
    style: str | None = None
    length: str | None = None
    focus: list[str] = []
    instructions: str | None = None


async def cover_letter_generate(db: Session, args: CoverLetterGenerateArgs) -> dict:
    payload = CoverLetterGenerateRequest(style=args.style, length=args.length, focus=args.focus, instructions=args.instructions)
    cl, error = await call_router(generate_job_cover_letter, job_id=args.job_id, payload=payload, db=db)
    if error:
        return {"success": False, "errors": [error]}
    return {"cover_letter_id": cl.id, "version_number": cl.version_number, "status": cl.status.value, "word_count": cl.word_count}


class CoverLetterApproveArgs(BaseModel):
    cover_letter_id: int


async def cover_letter_approve(db: Session, args: CoverLetterApproveArgs) -> dict:
    payload = CoverLetterStatusUpdateRequest(status=ApplicationMaterialStatus.APPROVED)
    cl, error = await call_router(update_cover_letter_status, cover_letter_id=args.cover_letter_id, payload=payload, db=db)
    if error:
        return {"success": False, "errors": [error]}
    return {"cover_letter_id": cl.id, "status": cl.status.value}


register(ToolSpec(
    name="cover_letter.generate", description="Generate a tailored cover letter for a job (local Ollama only, no paid API). Uses the job's latest CV version (approved if one exists, else the most recent draft).",
    input_schema=CoverLetterGenerateArgs, permission=ToolPermission.WRITE, risk=ToolRiskLevel.MEDIUM,
    side_effects=["creates_cover_letter"], handler=cover_letter_generate,
))
register(ToolSpec(
    name="cover_letter.approve", description="Mark a cover letter approved. Never called without the user having reviewed it.",
    input_schema=CoverLetterApproveArgs, permission=ToolPermission.WRITE, risk=ToolRiskLevel.MEDIUM,
    requires_approval=True, side_effects=["changes_cover_letter_status"], handler=cover_letter_approve,
))
