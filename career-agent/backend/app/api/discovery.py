import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.database import get_db
from app.discovery.base import ALL_SOURCES
from app.models.discovery_run import DiscoveryRun
from app.models.enums import DiscoveryTrigger
from app.schemas.discovery import (
    DiscoveryRunListResponse,
    DiscoveryRunRead,
    DiscoveryRunRequest,
    DiscoverySourceStatus,
)
from app.services.discovery_service import DiscoveryInputError, build_query, run_discovery

logger = logging.getLogger("app.api.discovery")

router = APIRouter(prefix="/discovery", tags=["discovery"])

_SOURCE_INFO = {
    "greenhouse": (False, "Searches the companies in your job-search goal's target_companies. No key required."),
    "lever": (False, "Searches the companies in your job-search goal's target_companies. No key required."),
    "remoteok": (False, "Searches all remote listings, filtered by your target roles. No key required."),
    "weworkremotely": (False, "Searches all listings, filtered by your target roles. No key required."),
    "adzuna": (True, "Free keyword+location search. Requires ADZUNA_APP_ID and ADZUNA_APP_KEY."),
    "usajobs": (True, "Free keyword+location search of U.S. federal roles. Requires USAJOBS_API_KEY and USAJOBS_USER_AGENT_EMAIL."),
    "remotive": (False, "Real keyword search across all-remote listings. No key required."),
    "arbeitnow": (False, "Searches all listings, filtered by your target roles. No key required."),
    "himalayas": (False, "Real keyword+location search across all-remote listings. No key required."),
}


@router.post("/run", response_model=DiscoveryRunRead, status_code=status.HTTP_201_CREATED)
def run_discovery_endpoint(payload: DiscoveryRunRequest, db: Session = Depends(get_db)):
    """Runs job discovery now, across the given sources (or every
    configured source if omitted), and stores any new jobs found. Safe to
    call repeatedly -- jobs already known (by external id, URL, or exact
    description) are recognized as duplicates, not re-created."""

    query = build_query(
        db,
        keywords_override=payload.keywords,
        locations_override=payload.locations,
        companies_override=payload.companies,
    )
    try:
        run = run_discovery(db, trigger=DiscoveryTrigger.MANUAL, sources=payload.sources, query=query)
    except DiscoveryInputError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))
    return run


@router.get("/runs", response_model=DiscoveryRunListResponse)
def list_discovery_runs(db: Session = Depends(get_db), limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0)):
    total = db.execute(select(func.count(DiscoveryRun.id))).scalar_one()
    items = db.execute(
        select(DiscoveryRun).order_by(DiscoveryRun.started_at.desc()).limit(limit).offset(offset)
    ).scalars().all()
    return DiscoveryRunListResponse(items=items, total=total)


@router.get("/runs/{run_id}", response_model=DiscoveryRunRead)
def get_discovery_run(run_id: int, db: Session = Depends(get_db)):
    run = db.get(DiscoveryRun, run_id)
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No discovery run with id={run_id}")
    return run


@router.get("/sources", response_model=list[DiscoverySourceStatus])
def list_discovery_sources():
    """What sources exist and whether they're ready to use -- Adzuna and
    USAJobs report configured=false until their API keys are set."""

    settings = get_settings()
    configured = {
        "greenhouse": True,
        "lever": True,
        "remoteok": True,
        "weworkremotely": True,
        "adzuna": bool(settings.adzuna_app_id and settings.adzuna_app_key),
        "usajobs": bool(settings.usajobs_api_key and settings.usajobs_user_agent_email),
        "remotive": True,
        "arbeitnow": True,
        "himalayas": True,
    }
    return [
        DiscoverySourceStatus(source=source, configured=configured[source], requires_api_key=_SOURCE_INFO[source][0], note=_SOURCE_INFO[source][1])
        for source in ALL_SOURCES
    ]
