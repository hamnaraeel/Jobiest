import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.ai.client import AIConfigurationError
from app.db.database import get_db
from app.models.enums import Recommendation
from app.models.job import Job
from app.models.job_match import JobMatch
from app.models.job_requirement import JobRequirement
from app.schemas.job import JobCreateRequest, JobCreateResponse, JobListResponse, JobRead
from app.schemas.job_match import JobMatchRead, JobSummaryRef, RequirementMatchDetail
from app.schemas.job_requirement import JobRequirementRead
from app.services.job_analysis_service import AIResponseError, AnalysisInputError, analyze_job
from app.services.job_ingestion_service import JobIngestionError, ingest_job
from app.services.job_matching_service import MatchInputError, compute_match

logger = logging.getLogger("app.api.jobs")

router = APIRouter(prefix="/jobs", tags=["jobs"])


def _get_job_or_404(db: Session, job_id: int) -> Job:
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No job with id={job_id}")
    return job


def _match_to_read(job: Job, match: JobMatch) -> JobMatchRead:
    def as_details(items: list[dict]) -> list[RequirementMatchDetail]:
        return [RequirementMatchDetail(**item) for item in items]

    return JobMatchRead(
        job=JobSummaryRef(title=job.title, company=job.company, location=job.location),
        score=match.overall_score,
        recommendation=match.recommendation,
        strengths=match.strengths,
        weaknesses=match.weaknesses,
        matched_requirements=as_details(match.matched_requirements),
        partial_requirements=as_details(match.partial_requirements),
        missing_requirements=as_details(match.missing_requirements),
        unknown_requirements=as_details(match.unknown_requirements),
        critical_gaps=match.critical_gaps,
        summary=match.reasoning_summary,
        created_at=match.created_at,
        updated_at=match.updated_at,
    )


@router.post("", response_model=JobCreateResponse, status_code=status.HTTP_201_CREATED)
def create_job(payload: JobCreateRequest, response: Response, db: Session = Depends(get_db)):
    """Ingest a job from a URL and/or a pasted description. Works with no
    OpenAI API key -- this stage only fetches/cleans/stores, it never
    calls the AI. Deduplicates on canonical URL or exact description text."""

    try:
        result = ingest_job(db, payload.url, payload.description)
    except JobIngestionError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))

    if not result.created:
        response.status_code = status.HTTP_200_OK
    return JobCreateResponse(job=JobRead.model_validate(result.job), created=result.created, fetch_notice=result.fetch_notice)


@router.get("", response_model=JobListResponse)
def list_jobs(
    db: Session = Depends(get_db),
    search: str | None = Query(None, description="Free-text search across title/company/description"),
    company: str | None = None,
    location: str | None = None,
    recommendation: Recommendation | None = None,
    min_score: int | None = Query(None, ge=0, le=100),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    stmt = select(Job).outerjoin(JobMatch, JobMatch.job_id == Job.id)
    count_stmt = select(func.count(Job.id.distinct())).select_from(Job).outerjoin(JobMatch, JobMatch.job_id == Job.id)

    conditions = []
    if search:
        pattern = f"%{search}%"
        conditions.append(or_(Job.title.ilike(pattern), Job.company.ilike(pattern), Job.description.ilike(pattern)))
    if company:
        conditions.append(Job.company.ilike(f"%{company}%"))
    if location:
        conditions.append(Job.location.ilike(f"%{location}%"))
    if recommendation:
        conditions.append(JobMatch.recommendation == recommendation)
    if min_score is not None:
        conditions.append(JobMatch.overall_score >= min_score)

    for condition in conditions:
        stmt = stmt.where(condition)
        count_stmt = count_stmt.where(condition)

    total = db.execute(count_stmt).scalar_one()
    jobs = db.execute(stmt.order_by(Job.created_at.desc()).limit(limit).offset(offset)).scalars().all()

    return JobListResponse(items=[JobRead.model_validate(j) for j in jobs], total=total, limit=limit, offset=offset)


@router.get("/{job_id}", response_model=JobRead)
def get_job(job_id: int, db: Session = Depends(get_db)):
    return _get_job_or_404(db, job_id)


@router.get("/{job_id}/requirements", response_model=list[JobRequirementRead])
def get_job_requirements(job_id: int, db: Session = Depends(get_db)):
    _get_job_or_404(db, job_id)
    rows = db.execute(select(JobRequirement).where(JobRequirement.job_id == job_id)).scalars().all()
    return rows


@router.post("/{job_id}/analyze", response_model=JobRead)
def analyze_job_endpoint(job_id: int, db: Session = Depends(get_db)):
    """Runs the one AI extraction call for this job and stores the
    resulting structured requirements. Requires OPENAI_API_KEY."""

    job = _get_job_or_404(db, job_id)
    try:
        return analyze_job(db, job)
    except AnalysisInputError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))
    except AIConfigurationError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc))
    except AIResponseError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc))


@router.post("/{job_id}/match", response_model=JobMatchRead)
def match_job_endpoint(job_id: int, db: Session = Depends(get_db)):
    """Runs (or re-runs) the deterministic match against the career
    profile. Auto-analyzes the job first if that hasn't happened yet."""

    job = _get_job_or_404(db, job_id)
    if not job.extracted_at:
        try:
            job = analyze_job(db, job)
        except AnalysisInputError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))
        except AIConfigurationError as exc:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc))
        except AIResponseError as exc:
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc))

    try:
        match = compute_match(db, job)
    except MatchInputError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))

    return _match_to_read(job, match)


@router.get("/{job_id}/match", response_model=JobMatchRead)
def get_job_match(job_id: int, db: Session = Depends(get_db)):
    job = _get_job_or_404(db, job_id)
    match = db.execute(select(JobMatch).where(JobMatch.job_id == job_id)).scalar_one_or_none()
    if match is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "This job has not been matched yet. POST /jobs/{job_id}/match first.")
    return _match_to_read(job, match)
