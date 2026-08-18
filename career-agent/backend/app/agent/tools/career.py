"""Read-only wrappers over Step 1 (Career Profile) and Step 7 (goals).
The agent never writes to the Career Profile itself -- see
permissions.ALWAYS_REQUIRES_APPROVAL and spec section 49 ("Profile
Integrity"); there is deliberately no career.update_profile tool."""

from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.agent.tool_registry import ToolSpec, register
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
