"""Step 8: Job Discovery orchestration.

Searches the enabled public, ToS-compliant job sources (Greenhouse/Lever
company boards, RemoteOK, We Work Remotely, Adzuna, USAJobs, Remotive,
Arbeitnow, Himalayas) using the career profile's target roles/locations
and the job-search goal's target companies (Step 7), then stores results
through the same dedup-aware ingest path Step 2 uses for manually-added
jobs. Deliberately excludes LinkedIn, Indeed, SimplyHired, and Wellfound
-- see app/discovery/base.py for why.

Each source is independent: one source erroring (bad API key, network
failure, unexpected response) is recorded against that source only and
never stops the others from running.
"""

import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.config import get_settings
from app.discovery.adzuna import search_adzuna
from app.discovery.arbeitnow import search_arbeitnow
from app.discovery.base import ALL_SOURCES, COMPANY_SOURCES, DiscoveredJob, DiscoveryQuery, DiscoverySourceError
from app.discovery.greenhouse import search_greenhouse
from app.discovery.himalayas import search_himalayas
from app.discovery.lever import search_lever
from app.discovery.remoteok import search_remoteok
from app.discovery.remotive import search_remotive
from app.discovery.usajobs import search_usajobs
from app.discovery.weworkremotely import search_weworkremotely
from app.models.discovery_run import DiscoveryRun
from app.models.enums import DiscoveryTrigger
from app.services import goal_service, profile_service
from app.services.job_ingestion_service import ingest_discovered_job

logger = logging.getLogger("app.discovery_service")


class DiscoveryInputError(ValueError):
    pass


def build_query(
    db: Session,
    limit_per_source: int | None = None,
    keywords_override: list[str] | None = None,
    locations_override: list[str] | None = None,
    companies_override: list[str] | None = None,
) -> DiscoveryQuery:
    """Builds the search query from what the user has already told the
    system, never invented: the current job-search goal's target_roles/
    target_locations/target_companies (Step 7) if set, falling back to
    the career profile's target_roles/preferred_locations (Step 1). Any
    of the three can be overridden for a single run (POST /discovery/run)
    without touching the stored goal/profile."""

    settings = get_settings()
    goal = goal_service.get_current_goal(db)
    profile = profile_service.get_default_profile(db)

    keywords = keywords_override
    if keywords is None:
        keywords = (goal.target_roles if goal and goal.target_roles else None) or (profile.target_roles if profile else []) or []

    locations = locations_override
    if locations is None:
        locations = (goal.target_locations if goal and goal.target_locations else None) or (profile.preferred_locations if profile else []) or []

    companies = companies_override
    if companies is None:
        companies = goal.target_companies if goal and goal.target_companies else []

    return DiscoveryQuery(
        keywords=list(keywords),
        locations=list(locations),
        companies=list(companies),
        limit_per_source=limit_per_source or settings.discovery_max_results_per_source,
    )


def _run_source(source: str, query: DiscoveryQuery) -> list[DiscoveredJob]:
    settings = get_settings()

    if source == "greenhouse":
        return search_greenhouse(query)
    if source == "lever":
        return search_lever(query)
    if source == "remoteok":
        return search_remoteok(query)
    if source == "weworkremotely":
        return search_weworkremotely(query)
    if source == "adzuna":
        return search_adzuna(query, settings.adzuna_app_id, settings.adzuna_app_key, settings.adzuna_country)
    if source == "usajobs":
        return search_usajobs(query, settings.usajobs_api_key, settings.usajobs_user_agent_email)
    if source == "remotive":
        return search_remotive(query)
    if source == "arbeitnow":
        return search_arbeitnow(query)
    if source == "himalayas":
        return search_himalayas(query)

    raise DiscoveryInputError(f"Unknown discovery source: {source}")


def run_discovery(
    db: Session,
    trigger: DiscoveryTrigger,
    sources: list[str] | None = None,
    query: DiscoveryQuery | None = None,
) -> DiscoveryRun:
    settings = get_settings()
    sources = sources or list(settings.discovery_enabled_sources)
    for source in sources:
        if source not in ALL_SOURCES:
            raise DiscoveryInputError(f"Unknown discovery source: {source}. Valid sources: {ALL_SOURCES}")

    resolved_query = query or build_query(db)
    started_at = datetime.now(timezone.utc)

    results: dict[str, dict] = {}
    total_found = 0
    total_created = 0

    for source in sources:
        if source in COMPANY_SOURCES and not resolved_query.companies:
            results[source] = {
                "found": 0, "created": 0, "duplicate": 0,
                "error": None,
                "note": "No target companies configured (set them via PUT /intelligence/goals) -- nothing to search.",
            }
            continue

        try:
            discovered_jobs = _run_source(source, resolved_query)
        except DiscoverySourceError as exc:
            logger.warning("discovery source failed source=%s error=%s", source, exc)
            results[source] = {"found": 0, "created": 0, "duplicate": 0, "error": str(exc)}
            continue
        except Exception as exc:  # noqa: BLE001 -- one source's bug must not sink the whole run
            logger.exception("discovery source raised an unexpected error source=%s", source)
            results[source] = {"found": 0, "created": 0, "duplicate": 0, "error": f"Unexpected error: {exc}"}
            continue

        created = 0
        for discovered in discovered_jobs:
            result = ingest_discovered_job(db, discovered)
            if result.created:
                created += 1

        results[source] = {"found": len(discovered_jobs), "created": created, "duplicate": len(discovered_jobs) - created, "error": None}
        total_found += len(discovered_jobs)
        total_created += created

    run = DiscoveryRun(
        trigger=trigger,
        sources=sources,
        query={"keywords": resolved_query.keywords, "locations": resolved_query.locations, "companies": resolved_query.companies},
        results=results,
        jobs_found=total_found,
        jobs_created=total_created,
        started_at=started_at,
        finished_at=datetime.now(timezone.utc),
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    logger.info("discovery run id=%s trigger=%s found=%s created=%s", run.id, trigger, total_found, total_created)

    return run
