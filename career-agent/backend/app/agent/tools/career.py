"""Read-only wrappers over Step 1 (Career Profile) and Step 7 (goals).
The agent never writes to the Career Profile itself -- see
permissions.ALWAYS_REQUIRES_APPROVAL and spec section 49 ("Profile
Integrity"); there is deliberately no career.update_profile tool.

career.confirm_resume_import is the one exception, and it's exactly as
gated: uploading/parsing a resume happens outside the agent (a real file
upload doesn't fit a chat message), but once a human has reviewed a
pending import, the agent can carry out their decision to confirm it --
still always through an explicit approval, never inferred."""

from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.agent.tool_registry import ToolSpec, register
from app.agent.tools._util import call_router
from app.models.enums import ToolPermission, ToolRiskLevel
from app.schemas.profile import CareerProfileRead
from app.schemas.recommendation import GoalProgressResponse, GoalRead
from app.services import goal_service, profile_service


class EmptyArgs(BaseModel):
    pass


async def get_profile(db: Session, args: EmptyArgs) -> dict:
    profile = profile_service.get_default_profile(db)
    if profile is None:
        return {"profile": None, "warning": "No career profile exists yet -- POST /profile or /profile/import first."}
    return {"profile": CareerProfileRead.model_validate(profile).model_dump(mode="json")}


async def get_goals(db: Session, args: EmptyArgs) -> dict:
    goal = goal_service.get_current_goal(db)
    if goal is None:
        return {"goal": None}
    return {"goal": GoalRead.model_validate(goal).model_dump(mode="json")}


async def get_goal_progress(db: Session, args: EmptyArgs) -> dict:
    goal = goal_service.get_current_goal(db)
    if goal is None:
        return {"goal": None, "progress": None, "warning": "No job-search goal configured yet."}
    progress = goal_service.goal_progress(db, goal)
    return GoalProgressResponse(goal=goal, progress=progress).model_dump(mode="json")


register(ToolSpec(
    name="career.get_profile", description="Read the career profile (name, target roles, skills counts, etc).",
    input_schema=EmptyArgs, permission=ToolPermission.READ_ONLY, risk=ToolRiskLevel.LOW, handler=get_profile,
))
register(ToolSpec(
    name="career.get_goals", description="Read the current job-search goal (target roles/locations/companies, limits).",
    input_schema=EmptyArgs, permission=ToolPermission.READ_ONLY, risk=ToolRiskLevel.LOW, handler=get_goals,
))
register(ToolSpec(
    name="career.get_goal_progress", description="Compare actual recent activity against the configured job-search goal.",
    input_schema=EmptyArgs, permission=ToolPermission.READ_ONLY, risk=ToolRiskLevel.LOW, handler=get_goal_progress,
))


async def list_resume_imports(db: Session, args: EmptyArgs) -> dict:
    from app.api.resume_import import list_resume_imports as _list_resume_imports
    result = _list_resume_imports(db=db)
    return result.model_dump(mode="json")


class ResumeImportIdArgs(BaseModel):
    resume_import_id: int


async def confirm_resume_import(db: Session, args: ResumeImportIdArgs) -> dict:
    from app.api.resume_import import confirm_resume_import as _confirm_resume_import
    from app.schemas.resume_import import ResumeImportConfirmRequest

    # confirm_resume_import returns the raw ORM CareerProfile row --
    # FastAPI's response_model normally validates it into CareerProfileRead
    # at the HTTP layer; done explicitly here for the same reason as
    # application.get and friends elsewhere in this package.
    profile, error = await call_router(_confirm_resume_import, import_id=args.resume_import_id, payload=ResumeImportConfirmRequest(), db=db)
    if error:
        return {"success": False, "errors": [error]}
    return {"profile": CareerProfileRead.model_validate(profile).model_dump(mode="json")}


register(ToolSpec(
    name="career.list_resume_imports", description="List uploaded resumes and what the AI proposed extracting from each, pending your review.",
    input_schema=EmptyArgs, permission=ToolPermission.READ_ONLY, risk=ToolRiskLevel.LOW, handler=list_resume_imports,
))
register(ToolSpec(
    name="career.confirm_resume_import",
    description="Write a pending resume import's extracted facts into the Career Profile, all as unverified. Always requires approval.",
    input_schema=ResumeImportIdArgs, permission=ToolPermission.WRITE, risk=ToolRiskLevel.MEDIUM,
    requires_approval=True, side_effects=["creates_profile_rows"], handler=confirm_resume_import,
))
