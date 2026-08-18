"""Step 3 wrappers: CV generation/preview/approval. cv.generate is
idempotent (spec section 38) -- it checks for an already-approved
version first rather than blindly generating a new one every time the
agent runs."""

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent.tool_registry import ToolSpec, register
from app.agent.tools._util import call_router
from app.api.cvs import generate_job_cv, list_cvs, preview_job_cv, update_cv_status
from app.models.cv_version import CVVersion
from app.models.enums import CVStatus, ToolPermission, ToolRiskLevel
from app.schemas.cv import CVStatusUpdateRequest


class CVGenerateArgs(BaseModel):
    job_id: int
    template_name: str = "ats/ml_engineer"
    compile_pdf: bool = True
    force: bool = False


async def cv_generate(db: Session, args: CVGenerateArgs) -> dict:
    if not args.force:
        existing = db.execute(
            select(CVVersion).where(CVVersion.job_id == args.job_id, CVVersion.status == CVStatus.APPROVED)
            .order_by(CVVersion.version_number.desc()).limit(1)
        ).scalar_one_or_none()
        if existing:
            return {
                "cv_version_id": existing.id, "version_number": existing.version_number, "status": existing.status.value,
                "reused_existing": True, "note": "An approved CV already exists for this job -- reused it instead of generating a duplicate. Pass force=true to generate anyway.",
            }

    from app.schemas.cv_generation import CVGenerateRequest
    payload = CVGenerateRequest(template_name=args.template_name, compile_pdf=args.compile_pdf)
    cv, error = await call_router(generate_job_cv, job_id=args.job_id, payload=payload, db=db)
    if error:
        return {"success": False, "errors": [error]}
    return {"cv_version_id": cv.id, "version_number": cv.version_number, "status": cv.status.value, "warnings": cv.warnings, "reused_existing": False}


async def cv_preview(db: Session, args: CVGenerateArgs) -> dict:
    from app.schemas.cv_generation import CVGenerateRequest
    payload = CVGenerateRequest(template_name=args.template_name, compile_pdf=False)
    result, error = await call_router(preview_job_cv, job_id=args.job_id, payload=payload, db=db)
    if error:
        return {"success": False, "errors": [error]}
    return result.model_dump(mode="json")


class CVListArgs(BaseModel):
    job_id: int | None = None


async def cv_list_versions(db: Session, args: CVListArgs) -> dict:
    # list_cvs has Query(...)-defaulted params that must all be passed
    # explicitly when called directly -- see jobs.jobs_search's comment.
    result = list_cvs(db=db, job_id=args.job_id, status_filter=None, limit=20, offset=0)
    return result.model_dump(mode="json")


class CVApproveArgs(BaseModel):
    cv_version_id: int


async def cv_approve(db: Session, args: CVApproveArgs) -> dict:
    payload = CVStatusUpdateRequest(status=CVStatus.APPROVED)
    cv, error = await call_router(update_cv_status, cv_id=args.cv_version_id, payload=payload, db=db)
    if error:
        return {"success": False, "errors": [error]}
    return {"cv_version_id": cv.id, "status": cv.status.value}


register(ToolSpec(
    name="cv.generate", description="Generate a tailored CV for a job (idempotent: reuses an already-approved version unless force=true).",
    input_schema=CVGenerateArgs, permission=ToolPermission.WRITE, risk=ToolRiskLevel.MEDIUM,
    side_effects=["creates_cv_version"], handler=cv_generate,
))
register(ToolSpec(
    name="cv.validate", description="Preview/validate generated CV content without compiling a PDF.",
    input_schema=CVGenerateArgs, permission=ToolPermission.WRITE, risk=ToolRiskLevel.MEDIUM,
    side_effects=["creates_cv_version"], handler=cv_preview,
))
register(ToolSpec(
    name="cv.list_versions", description="List CV versions, optionally filtered by job.",
    input_schema=CVListArgs, permission=ToolPermission.READ_ONLY, risk=ToolRiskLevel.LOW, handler=cv_list_versions,
))
register(ToolSpec(
    name="cv.approve", description="Mark a CV version approved -- the only way it becomes eligible for an application. Never called without the user having reviewed it.",
    input_schema=CVApproveArgs, permission=ToolPermission.WRITE, risk=ToolRiskLevel.MEDIUM,
    requires_approval=True, side_effects=["changes_cv_status"], handler=cv_approve,
))
