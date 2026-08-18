"""Step 6 analytics wrappers -- pure reads over already-computed
deterministic (SQL/Python, no LLM) analytics."""

from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.agent.tool_registry import ToolSpec, register
from app.api.intelligence import get_weekly_review
from app.api.tracking import get_dashboard
from app.models.enums import ToolPermission, ToolRiskLevel
from app.schemas.analytics import DashboardResponse


class EmptyArgs(BaseModel):
    pass


async def analytics_overview(db: Session, args: EmptyArgs) -> dict:
    # get_dashboard returns a plain dict -- FastAPI's response_model
    # normally validates it into DashboardResponse at the HTTP layer;
    # calling the function directly skips that, so it's done explicitly here.
    result = get_dashboard(db=db)
    return DashboardResponse.model_validate(result).model_dump(mode="json")


async def analytics_weekly_review(db: Session, args: EmptyArgs) -> dict:
    result = get_weekly_review(db=db)
    return result.model_dump(mode="json")


register(ToolSpec(
    name="analytics.overview", description="The full dashboard: funnel, conversion rates, time-to-X, upcoming items.",
    input_schema=EmptyArgs, permission=ToolPermission.READ_ONLY, risk=ToolRiskLevel.LOW, handler=analytics_overview,
))
register(ToolSpec(
    name="analytics.weekly_review", description="This week's applications/responses/interviews plus a skill-gap observation.",
    input_schema=EmptyArgs, permission=ToolPermission.READ_ONLY, risk=ToolRiskLevel.LOW, handler=analytics_weekly_review,
))
