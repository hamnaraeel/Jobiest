"""Step 5/6/7 wrappers: prepare, review, browser-fill, and submit
applications, plus tracking search/status/intelligence.

application.approve_submission and application.submit are the one place
this whole agent is most careful: both are EXTERNAL_ACTION + HIGH risk,
requires_approval=True with no override, and application.submit still
goes through Step 5's own independent DRY_RUN + submission_guard check
underneath -- the agent's approval gate does not replace that gate, it
sits in front of it. Two independent things both have to agree before a
real click happens."""

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.agent.tool_registry import ToolSpec, register
from app.agent.tools._util import call_router
from app.api.browser_applications import (
    analyze_page,
    approve_submission as _approve_submission_endpoint,
    create_application,
    fill,
    get_application,
    get_review,
    pause as _pause_endpoint,
    resume as _resume_endpoint,
    start_browser,
    submit as _submit_endpoint,
)
from app.api.intelligence import get_application_intelligence, get_interview_preparation
from app.api.tracking import get_readiness, search_applications as _search_applications, update_application_status
from app.models.application import Application
from app.models.enums import ApplicationPlatform, ApplicationStatus, PriorityLevel, ToolPermission, ToolRiskLevel
from app.schemas.application import ApplicationCreateRequest, ApplicationRead
from app.schemas.tracking import ApplicationStatusUpdateRequest, ReadinessResponse


class ApplicationPrepareArgs(BaseModel):
    job_id: int
    cv_version_id: int | None = None
    cover_letter_id: int | None = None
    application_url: str | None = None
    source: str | None = None
    force: bool = False


async def application_prepare(db: Session, args: ApplicationPrepareArgs) -> dict:
    from app.models.job import Job
    job = db.get(Job, args.job_id)
    if job is None:
        return {"success": False, "errors": [f"No job with id={args.job_id}."]}
    payload = ApplicationCreateRequest(
        application_url=args.application_url, cv_version_id=args.cv_version_id,
        cover_letter_id=args.cover_letter_id, force=args.force, source=args.source,
    )
    application, error = await call_router(create_application, job_id=args.job_id, payload=payload, db=db)
    if error:
        return {"success": False, "errors": [error]}
    return {"application_id": application.id, "status": application.status.value, "platform": application.platform.value}


class ApplicationPrepareBatchArgs(BaseModel):
    job_ids: list[int] = Field(default_factory=list, max_length=20, description="Empty is valid -- means nothing was selected to prepare.")


async def application_prepare_batch(db: Session, args: ApplicationPrepareBatchArgs) -> dict:
    """The composite step behind "prepare applications for the top N
    jobs" (spec sections 17/56): per job, generate a CV, generate a
    cover letter, then create the Application row attaching those exact
    (still-draft) versions. Each is the same handler cv.generate /
    cover_letter.generate / application.prepare would run on its own --
    called directly here rather than as separate plan steps because the
    job count isn't known until jobs.rank runs, so it can't be a fixed
    number of AgentPlanStep rows. One job failing doesn't stop the rest
    (spec section 21)."""

    from app.agent.tools.cover_letter import CoverLetterGenerateArgs, cover_letter_generate
    from app.agent.tools.cv import CVGenerateArgs, cv_generate

    prepared, failed = [], []
    for job_id in args.job_ids:
        cv_result = await cv_generate(db, CVGenerateArgs(job_id=job_id))
        if cv_result.get("success") is False:
            failed.append({"job_id": job_id, "stage": "cv.generate", "errors": cv_result.get("errors")})
            continue

        cl_result = await cover_letter_generate(db, CoverLetterGenerateArgs(job_id=job_id))
        if cl_result.get("success") is False:
            failed.append({"job_id": job_id, "stage": "cover_letter.generate", "errors": cl_result.get("errors")})
            continue

        prepare_result = await application_prepare(db, ApplicationPrepareArgs(
            job_id=job_id, cv_version_id=cv_result["cv_version_id"], cover_letter_id=cl_result["cover_letter_id"],
        ))
        if prepare_result.get("success") is False:
            failed.append({"job_id": job_id, "stage": "application.prepare", "errors": prepare_result.get("errors")})
            continue

        prepared.append({
            "job_id": job_id, "application_id": prepare_result["application_id"],
            "cv_version_id": cv_result["cv_version_id"], "cover_letter_id": cl_result["cover_letter_id"],
        })

    return {"prepared": prepared, "failed": failed, "application_ids": [p["application_id"] for p in prepared]}


class ApplicationSearchArgs(BaseModel):
    company: str | None = None
    role: str | None = None
    status: ApplicationStatus | None = None
    platform: ApplicationPlatform | None = None
    priority: PriorityLevel | None = None
    include_archived: bool = False
    sort: str = "newest"
    limit: int = 20


async def application_search(db: Session, args: ApplicationSearchArgs) -> dict:
    # See jobs_search's comment -- tracking.search_applications has
    # Query(...)-defaulted params that must all be passed explicitly
    # when called directly.
    result = _search_applications(
        db=db, company=args.company, role=args.role, status_filter=args.status, platform=args.platform,
        priority=args.priority, min_match_score=None, submitted_after=None, submitted_before=None,
        include_archived=args.include_archived, sort=args.sort, limit=args.limit, offset=0,
    )
    return result.model_dump(mode="json")


class ApplicationIdArgs(BaseModel):
    application_id: int


async def application_get(db: Session, args: ApplicationIdArgs) -> dict:
    # get_application returns the raw ORM Application row -- FastAPI's
    # response_model normally validates it into ApplicationRead at the
    # HTTP layer; done explicitly here instead.
    result, error = await call_router(get_application, application_id=args.application_id, db=db)
    if error:
        return {"success": False, "errors": [error]}
    return {"application": ApplicationRead.model_validate(result).model_dump(mode="json")}


async def application_review(db: Session, args: ApplicationIdArgs) -> dict:
    result, error = await call_router(get_review, application_id=args.application_id, db=db)
    if error:
        return {"success": False, "errors": [error]}
    return result.model_dump(mode="json")


async def application_get_readiness(db: Session, args: ApplicationIdArgs) -> dict:
    # check_readiness returns a plain dict -- validated here for the
    # same reason as application_get above.
    result, error = await call_router(get_readiness, application_id=args.application_id, db=db)
    if error:
        return {"success": False, "errors": [error]}
    return ReadinessResponse.model_validate(result).model_dump(mode="json")


async def application_get_intelligence(db: Session, args: ApplicationIdArgs) -> dict:
    result, error = await call_router(get_application_intelligence, application_id=args.application_id, db=db)
    if error:
        return {"success": False, "errors": [error]}
    return result.model_dump(mode="json")


async def application_get_interview_preparation(db: Session, args: ApplicationIdArgs) -> dict:
    result, error = await call_router(get_interview_preparation, application_id=args.application_id, db=db)
    if error:
        return {"success": False, "errors": [error]}
    return result.model_dump(mode="json")


async def application_start(db: Session, args: ApplicationIdArgs) -> dict:
    application, error = await call_router(start_browser, application_id=args.application_id, db=db)
    if error:
        return {"success": False, "errors": [error]}
    return {"application_id": application.id, "status": application.status.value}


async def application_analyze_page(db: Session, args: ApplicationIdArgs) -> dict:
    result, error = await call_router(analyze_page, application_id=args.application_id, db=db)
    if error:
        return {"success": False, "errors": [error]}
    return result.model_dump(mode="json")


async def application_fill(db: Session, args: ApplicationIdArgs) -> dict:
    result, error = await call_router(fill, application_id=args.application_id, db=db)
    if error:
        return {"success": False, "errors": [error]}
    return result.model_dump(mode="json")


async def application_pause(db: Session, args: ApplicationIdArgs) -> dict:
    application, error = await call_router(_pause_endpoint, application_id=args.application_id, db=db)
    if error:
        return {"success": False, "errors": [error]}
    return {"application_id": application.id, "status": application.status.value}


async def application_resume(db: Session, args: ApplicationIdArgs) -> dict:
    application, error = await call_router(_resume_endpoint, application_id=args.application_id, db=db)
    if error:
        return {"success": False, "errors": [error]}
    return {"application_id": application.id, "status": application.status.value}


async def application_approve_submission(db: Session, args: ApplicationIdArgs) -> dict:
    """Only reached once the agent's own approval gate has already been
    granted (spec section 13) -- this then flips the *independent* Step
    5 submission_approved flag, which is the one submit() itself checks."""

    application, error = await call_router(_approve_submission_endpoint, application_id=args.application_id, db=db)
    if error:
        return {"success": False, "errors": [error]}
    return {"application_id": application.id, "submission_approved": application.submission_approved}


async def application_submit(db: Session, args: ApplicationIdArgs) -> dict:
    """The agent-level approval on THIS step is what the user is
    actually granting when they say "submit" -- approve_submission is
    mechanically required first (it's the only way
    Application.submission_approved becomes True) but is not a second
    decision point, so it's chained here rather than being its own
    separately-approved plan step."""

    application = db.get(Application, args.application_id)
    if application is None:
        return {"success": False, "errors": [f"No application with id={args.application_id}."]}

    if not application.submission_approved:
        _, error = await call_router(_approve_submission_endpoint, application_id=args.application_id, db=db)
        if error:
            return {"success": False, "errors": [error]}

    result, error = await call_router(_submit_endpoint, application_id=args.application_id, db=db)
    if error:
        return {"success": False, "errors": [error]}
    return result.model_dump(mode="json")


class ApplicationUpdateStatusArgs(BaseModel):
    application_id: int
    status: ApplicationStatus
    reason: str | None = None


async def application_update_status(db: Session, args: ApplicationUpdateStatusArgs) -> dict:
    payload = ApplicationStatusUpdateRequest(status=args.status, reason=args.reason)
    application, error = await call_router(update_application_status, application_id=args.application_id, payload=payload, db=db)
    if error:
        return {"success": False, "errors": [error]}
    return {"application_id": application.id, "status": application.status.value}


register(ToolSpec(
    name="application.prepare", description="Create an application attempt for a job, attaching the given (or latest approved) CV/cover letter.",
    input_schema=ApplicationPrepareArgs, permission=ToolPermission.WRITE, risk=ToolRiskLevel.MEDIUM,
    side_effects=["creates_application"], handler=application_prepare,
))
register(ToolSpec(
    name="application.prepare_batch", description="Generate a CV + cover letter and create an application for each of several jobs in one call.",
    input_schema=ApplicationPrepareBatchArgs, permission=ToolPermission.WRITE, risk=ToolRiskLevel.MEDIUM,
    side_effects=["creates_cv_versions", "creates_cover_letters", "creates_applications"], handler=application_prepare_batch,
))
register(ToolSpec(
    name="applications.search", description="Search/filter/sort applications.",
    input_schema=ApplicationSearchArgs, permission=ToolPermission.READ_ONLY, risk=ToolRiskLevel.LOW, handler=application_search,
))
register(ToolSpec(
    name="application.get", description="Fetch one application by id.",
    input_schema=ApplicationIdArgs, permission=ToolPermission.READ_ONLY, risk=ToolRiskLevel.LOW, handler=application_get,
))
register(ToolSpec(
    name="application.review", description="Review an application's filled/missing fields and warnings.",
    input_schema=ApplicationIdArgs, permission=ToolPermission.READ_ONLY, risk=ToolRiskLevel.LOW, handler=application_review,
))
register(ToolSpec(
    name="application.get_readiness", description="Check whether an application has everything needed (match, CV, cover letter, questions).",
    input_schema=ApplicationIdArgs, permission=ToolPermission.READ_ONLY, risk=ToolRiskLevel.LOW, handler=application_get_readiness,
))
register(ToolSpec(
    name="application.get_intelligence", description="Step 7 intelligence for one application (quality score, gaps, follow-up recommendation).",
    input_schema=ApplicationIdArgs, permission=ToolPermission.READ_ONLY, risk=ToolRiskLevel.LOW, handler=application_get_intelligence,
))
register(ToolSpec(
    name="interview.prepare", description="Assemble interview-preparation context for an application (job description, CV, matched skills).",
    input_schema=ApplicationIdArgs, permission=ToolPermission.READ_ONLY, risk=ToolRiskLevel.LOW, handler=application_get_interview_preparation,
))
register(ToolSpec(
    name="application.start", description="Open a real (Playwright) browser session against the application's URL.",
    input_schema=ApplicationIdArgs, permission=ToolPermission.EXTERNAL_ACTION, risk=ToolRiskLevel.MEDIUM,
    side_effects=["opens_browser"], handler=application_start,
))
register(ToolSpec(
    name="application.analyze_page", description="Detect form fields / CAPTCHA / login-required on the open application page.",
    input_schema=ApplicationIdArgs, permission=ToolPermission.EXTERNAL_ACTION, risk=ToolRiskLevel.LOW, handler=application_analyze_page,
))
register(ToolSpec(
    name="application.fill", description="Auto-fill high-confidence fields and upload approved materials. Never fills salary/authorization/relocation.",
    input_schema=ApplicationIdArgs, permission=ToolPermission.EXTERNAL_ACTION, risk=ToolRiskLevel.MEDIUM,
    side_effects=["fills_external_form"], handler=application_fill,
))
register(ToolSpec(
    name="application.pause", description="Pause an in-progress browser application session.",
    input_schema=ApplicationIdArgs, permission=ToolPermission.WRITE, risk=ToolRiskLevel.LOW, handler=application_pause,
))
register(ToolSpec(
    name="application.resume", description="Resume a paused browser application session.",
    input_schema=ApplicationIdArgs, permission=ToolPermission.WRITE, risk=ToolRiskLevel.LOW, handler=application_resume,
))
register(ToolSpec(
    name="application.approve_submission", description="Flip the (independent) Step 5 submission-approved flag. HIGH risk -- always requires explicit approval.",
    input_schema=ApplicationIdArgs, permission=ToolPermission.EXTERNAL_ACTION, risk=ToolRiskLevel.HIGH,
    requires_approval=True, side_effects=["approves_submission"], handler=application_approve_submission,
))
register(ToolSpec(
    name="application.submit", description="Submit the application. Still gated by DRY_RUN and submission_guard underneath. HIGH risk -- always requires explicit approval.",
    input_schema=ApplicationIdArgs, permission=ToolPermission.EXTERNAL_ACTION, risk=ToolRiskLevel.HIGH,
    requires_approval=True, side_effects=["submits_external_application"], handler=application_submit,
))
register(ToolSpec(
    name="application.update_status", description="Manually record a status change (e.g. recruiter contact, interview scheduled).",
    input_schema=ApplicationUpdateStatusArgs, permission=ToolPermission.WRITE, risk=ToolRiskLevel.MEDIUM,
    side_effects=["changes_application_status"], handler=application_update_status,
))
