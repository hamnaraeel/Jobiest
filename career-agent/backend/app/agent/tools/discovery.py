"""Step 2b (job discovery) wrappers."""

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.agent.tool_registry import ToolSpec, register
from app.models.enums import DiscoveryTrigger, ToolPermission, ToolRiskLevel
from app.services.discovery_service import DiscoveryInputError, build_query, run_discovery


class DiscoveryRunArgs(BaseModel):
    sources: list[str] | None = None
    keywords: list[str] | None = Field(None, description="Overrides the profile/goal-derived keywords for this run only.")
    locations: list[str] | None = None


async def discovery_run(db: Session, args: DiscoveryRunArgs) -> dict:
    query = build_query(db, keywords_override=args.keywords, locations_override=args.locations)
    try:
        run = run_discovery(db, trigger=DiscoveryTrigger.MANUAL, sources=args.sources, query=query)
    except DiscoveryInputError as exc:
        return {"success": False, "errors": [str(exc)]}
    return {
        "run_id": run.id, "jobs_found": run.jobs_found, "jobs_created": run.jobs_created,
        "results": run.results,
    }


class EmptyArgs(BaseModel):
    pass


async def discovery_sources(db: Session, args: EmptyArgs) -> dict:
    from app.config import get_settings

    settings = get_settings()
    return {
        "sources": {
            "greenhouse": True, "lever": True, "remoteok": True, "weworkremotely": True,
            "adzuna": bool(settings.adzuna_app_id and settings.adzuna_app_key),
            "usajobs": bool(settings.usajobs_api_key and settings.usajobs_user_agent_email),
        }
    }


register(ToolSpec(
    name="discovery.run", description="Search public job sources (Greenhouse/Lever/RemoteOK/WWR/Adzuna/USAJobs) and store new matches.",
    input_schema=DiscoveryRunArgs, permission=ToolPermission.WRITE, risk=ToolRiskLevel.MEDIUM,
    side_effects=["creates_job_rows"], handler=discovery_run,
))
register(ToolSpec(
    name="discovery.sources", description="Which discovery sources are configured/ready.",
    input_schema=EmptyArgs, permission=ToolPermission.READ_ONLY, risk=ToolRiskLevel.LOW, handler=discovery_sources,
))
