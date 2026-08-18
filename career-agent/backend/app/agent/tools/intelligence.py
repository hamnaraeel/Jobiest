"""Step 7 wrappers: recommendations, skill gaps, career strategy."""

from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.agent.tool_registry import ToolSpec, register
from app.api.intelligence import (
    accept_recommendation,
    generate_recommendations,
    get_career_intelligence,
    get_skill_gaps,
    get_strategy,
    list_recommendations,
)
from app.agent.tools._util import call_router
from app.models.enums import RecommendationStatus, RecommendationType, ToolPermission, ToolRiskLevel
from app.schemas.recommendation import RecommendationRead


class EmptyArgs(BaseModel):
    pass


async def intelligence_generate_recommendations(db: Session, args: EmptyArgs) -> dict:
    result = generate_recommendations(db=db)
    return result.model_dump(mode="json")


class RecommendationsListArgs(BaseModel):
    status: RecommendationStatus | None = None
    type: RecommendationType | None = None


async def intelligence_list_recommendations(db: Session, args: RecommendationsListArgs) -> dict:
    result = list_recommendations(db=db, status_filter=args.status, type=args.type)
    return result.model_dump(mode="json")


class RecommendationIdArgs(BaseModel):
    recommendation_id: int


async def intelligence_accept_recommendation(db: Session, args: RecommendationIdArgs) -> dict:
    # accept_recommendation returns the raw ORM row -- validated here
    # for the same reason as application.get above.
    result, error = await call_router(accept_recommendation, recommendation_id=args.recommendation_id, db=db)
    if error:
        return {"success": False, "errors": [error]}
    return RecommendationRead.model_validate(result).model_dump(mode="json")


async def intelligence_skill_gaps(db: Session, args: EmptyArgs) -> dict:
    result = get_skill_gaps(db=db)
    return result.model_dump(mode="json")


async def intelligence_career(db: Session, args: EmptyArgs) -> dict:
    result = get_career_intelligence(db=db)
    return result.model_dump(mode="json")


async def intelligence_strategy(db: Session, args: EmptyArgs) -> dict:
    result = get_strategy(db=db)
    return result.model_dump(mode="json")


register(ToolSpec(
    name="intelligence.generate_recommendations", description="Generate fresh recommendations from current history (job priorities, skill gaps, CV improvements, rejection patterns...).",
    input_schema=EmptyArgs, permission=ToolPermission.WRITE, risk=ToolRiskLevel.MEDIUM,
    side_effects=["creates_recommendation_rows"], handler=intelligence_generate_recommendations,
))
register(ToolSpec(
    name="intelligence.recommendations", description="List existing recommendations, optionally filtered by status/type.",
    input_schema=RecommendationsListArgs, permission=ToolPermission.READ_ONLY, risk=ToolRiskLevel.LOW, handler=intelligence_list_recommendations,
))
register(ToolSpec(
    name="intelligence.accept_recommendation", description="Mark a recommendation accepted (the user's own decision, recorded).",
    input_schema=RecommendationIdArgs, permission=ToolPermission.WRITE, risk=ToolRiskLevel.LOW, handler=intelligence_accept_recommendation,
))
register(ToolSpec(
    name="intelligence.skill_gaps", description="Skills frequently requested in analyzed jobs that the profile doesn't show.",
    input_schema=EmptyArgs, permission=ToolPermission.READ_ONLY, risk=ToolRiskLevel.LOW, handler=intelligence_skill_gaps,
))
register(ToolSpec(
    name="intelligence.career", description="Strongest roles/skills, application performance, career-direction observation.",
    input_schema=EmptyArgs, permission=ToolPermission.READ_ONLY, risk=ToolRiskLevel.LOW, handler=intelligence_career,
))
register(ToolSpec(
    name="intelligence.strategy", description="Personalized strategy: strengths/weaknesses, best-performing role/source, suggested weekly targets.",
    input_schema=EmptyArgs, permission=ToolPermission.READ_ONLY, risk=ToolRiskLevel.LOW, handler=intelligence_strategy,
))
