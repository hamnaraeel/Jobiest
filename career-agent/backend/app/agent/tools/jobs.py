"""Step 2/6/7 wrappers: search, analyze, match, and rank jobs. Every
handler calls the exact function the corresponding HTTP endpoint calls
-- jobs.search reuses tracking.search_jobs, jobs.analyze reuses
job_analysis_service.analyze_job, etc. jobs.rank is the one genuinely
*orchestration*-level tool here: it composes per-job intelligence
(already computed by Step 7's job_prioritizer) across several jobs into
a sorted list, which no single existing endpoint does on its own."""

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.agent.tool_registry import ToolSpec, register
from app.api.tracking import search_jobs as _search_jobs
from app.intelligence.application_analyzer import build_job_strategy
from app.models.enums import JobStatus, PriorityLevel, ToolPermission, ToolRiskLevel
from app.models.job import Job
from app.schemas.job import JobRead
from app.ai.client import AIConfigurationError
from app.services.job_analysis_service import AnalysisInputError, analyze_job
from app.services.job_matching_service import MatchInputError, compute_match
from app.services.profile_service import get_default_profile


class JobsSearchArgs(BaseModel):
    company: str | None = None
    role: str | None = Field(None, description="Matches job title.")
    status: JobStatus | None = None
    priority: PriorityLevel | None = None
    location: str | None = None
    remote: bool | None = None
    min_match_score: int | None = Field(None, ge=0, le=100)
    sort: str = "newest"
    limit: int = Field(20, ge=1, le=100)


async def jobs_search(db: Session, args: JobsSearchArgs) -> dict:
    # tracking.search_jobs has several FastAPI Query(...)-defaulted
    # params -- calling it directly (bypassing FastAPI's own dependency
    # injection) means every one of them must be passed explicitly, or
    # the raw Query() marker object leaks through as the "value" and
    # breaks the SQL query. tag/source/discovered_after/discovered_before
    # use plain None defaults so they're safe to omit; offset does not.
    result = _search_jobs(
        db=db, company=args.company, role=args.role, status_filter=args.status, priority=args.priority,
        location=args.location, remote=args.remote, min_match_score=args.min_match_score, sort=args.sort,
        limit=args.limit, offset=0,
    )
    return result.model_dump(mode="json")


class JobIdArgs(BaseModel):
    job_id: int


async def jobs_get(db: Session, args: JobIdArgs) -> dict:
    job = db.get(Job, args.job_id)
    if job is None:
        return {"job": None, "warning": f"No job with id={args.job_id}."}
    return {"job": JobRead.model_validate(job).model_dump(mode="json")}


async def jobs_analyze(db: Session, args: JobIdArgs) -> dict:
    job = db.get(Job, args.job_id)
    if job is None:
        return {"success": False, "errors": [f"No job with id={args.job_id}."]}
    try:
        job = analyze_job(db, job)
    except (AnalysisInputError, AIConfigurationError) as exc:
        return {"success": False, "errors": [str(exc)]}
    return {"job": JobRead.model_validate(job).model_dump(mode="json")}


async def jobs_match(db: Session, args: JobIdArgs) -> dict:
    job = db.get(Job, args.job_id)
    if job is None:
        return {"success": False, "errors": [f"No job with id={args.job_id}."]}
    if not job.extracted_at:
        try:
            job = analyze_job(db, job)
        except (AnalysisInputError, AIConfigurationError) as exc:
            return {"success": False, "errors": [str(exc)]}
    try:
        match = compute_match(db, job)
    except MatchInputError as exc:
        return {"success": False, "errors": [str(exc)]}
    return {"score": match.overall_score, "recommendation": match.recommendation.value, "job_id": job.id}


class JobsRankArgs(BaseModel):
    job_ids: list[int] = Field(default_factory=list, max_length=50, description="Empty is valid -- means the search this feeds from found nothing.")
    top_n: int | None = Field(None, ge=1, description="Trim the ranked result to this many jobs.")


async def jobs_rank(db: Session, args: JobsRankArgs) -> dict:
    """Composes three already-existing steps per job -- analyze (if not
    already), match (if not already), then Step 7's priority scoring --
    into one ranked list. Each sub-step is the same function
    jobs.analyze/jobs.match call; a job that fails analysis (e.g. no
    OPENAI_API_KEY configured) is skipped with a note, not fatal to the
    rest of the batch."""

    profile = get_default_profile(db)
    ranked = []
    skipped = []
    for job_id in args.job_ids:
        job = db.get(Job, job_id)
        if job is None:
            continue
        try:
            if not job.extracted_at:
                job = analyze_job(db, job)
            if not job.match:
                compute_match(db, job)
                db.refresh(job)
        except (AnalysisInputError, MatchInputError, AIConfigurationError) as exc:
            skipped.append({"job_id": job_id, "reason": str(exc)})
            continue

        strategy = build_job_strategy(db, job, profile)
        ranked.append({
            "job_id": job.id, "title": job.title, "company": job.company,
            "priority_score": strategy.priority.score, "opportunity_score": strategy.opportunity.score,
            "reasons": strategy.priority.reasons,
        })

    ranked.sort(key=lambda r: r["priority_score"], reverse=True)
    if args.top_n:
        ranked = ranked[:args.top_n]
    return {"ranked": ranked, "ranked_job_ids": [r["job_id"] for r in ranked], "skipped": skipped}


register(ToolSpec(
    name="jobs.search", description="Search/filter/sort jobs (company, role, status, priority, location, remote, match score).",
    input_schema=JobsSearchArgs, permission=ToolPermission.READ_ONLY, risk=ToolRiskLevel.LOW, handler=jobs_search,
))
register(ToolSpec(
    name="jobs.get", description="Fetch one job by id.",
    input_schema=JobIdArgs, permission=ToolPermission.READ_ONLY, risk=ToolRiskLevel.LOW, handler=jobs_get,
))
register(ToolSpec(
    name="jobs.analyze", description="Run AI requirement extraction on a job (requires OPENAI_API_KEY).",
    input_schema=JobIdArgs, permission=ToolPermission.WRITE, risk=ToolRiskLevel.MEDIUM,
    side_effects=["creates_job_requirements"], handler=jobs_analyze,
))
register(ToolSpec(
    name="jobs.match", description="Compute the deterministic match score against the career profile (auto-analyzes first if needed).",
    input_schema=JobIdArgs, permission=ToolPermission.WRITE, risk=ToolRiskLevel.MEDIUM,
    side_effects=["creates_or_updates_job_match"], handler=jobs_match,
))
register(ToolSpec(
    name="jobs.rank", description="Analyze+match (if not already done) then rank a set of jobs by Step 7's priority score (highest first). Optionally trims to top_n.",
    input_schema=JobsRankArgs, permission=ToolPermission.WRITE, risk=ToolRiskLevel.MEDIUM,
    side_effects=["creates_job_requirements", "creates_or_updates_job_match"], handler=jobs_rank,
))
