"""Browser-assisted job application endpoints (Step 5). This is an
ASSISTED workflow: fields are only ever auto-filled at high confidence,
files are only uploaded from approved CV/cover-letter materials, and a
real submit click can only ever happen after both DRY_RUN is disabled
AND the user has explicitly called approve-submission -- see
app/browser/submission_guard.py for the actual gate.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.browser import browser_manager
from app.config import get_settings
from app.db.database import get_db
from app.models.application import Application
from app.models.application_event import ApplicationEvent
from app.models.application_field import ApplicationField
from app.models.job import Job
from app.schemas.application import (
    ApplicationCreateRequest,
    ApplicationEventRead,
    ApplicationFieldRead,
    ApplicationListResponse,
    ApplicationRead,
    ApplicationReviewResponse,
    FillResultResponse,
    PageAnalysisResponse,
    SubmitResultResponse,
    UserInputRequest,
)
from app.services import application_service
from app.services.application_service import ApplicationInputError, DuplicateApplicationError

logger = logging.getLogger("app.api.browser_applications")

apply_router = APIRouter(prefix="/jobs", tags=["browser-applications"])
applications_router = APIRouter(prefix="/applications", tags=["browser-applications"])


def _get_job_or_404(db: Session, job_id: int) -> Job:
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No job with id={job_id}")
    return job


def _get_application_or_404(db: Session, application_id: int) -> Application:
    application = db.get(Application, application_id)
    if application is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No application with id={application_id}")
    return application


@apply_router.post("/{job_id}/apply", response_model=ApplicationRead, status_code=status.HTTP_201_CREATED)
def create_application(job_id: int, payload: ApplicationCreateRequest = ApplicationCreateRequest(), db: Session = Depends(get_db)):
    job = _get_job_or_404(db, job_id)
    try:
        return application_service.create_application(
            db, job, application_url=payload.application_url,
            cv_version_id=payload.cv_version_id, cover_letter_id=payload.cover_letter_id, force=payload.force,
        )
    except DuplicateApplicationError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc))
    except ApplicationInputError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))


@applications_router.get("", response_model=ApplicationListResponse)
def list_applications(job_id: int | None = Query(default=None), db: Session = Depends(get_db)):
    stmt = select(Application)
    if job_id is not None:
        stmt = stmt.where(Application.job_id == job_id)
    items = db.execute(stmt.order_by(Application.id.desc())).scalars().all()
    return ApplicationListResponse(items=list(items), total=len(items))


@applications_router.get("/{application_id}", response_model=ApplicationRead)
def get_application(application_id: int, db: Session = Depends(get_db)):
    return _get_application_or_404(db, application_id)


@applications_router.get("/{application_id}/events", response_model=list[ApplicationEventRead])
def list_application_events(application_id: int, db: Session = Depends(get_db)):
    _get_application_or_404(db, application_id)
    return db.execute(
        select(ApplicationEvent).where(ApplicationEvent.application_id == application_id).order_by(ApplicationEvent.timestamp)
    ).scalars().all()


@applications_router.post("/{application_id}/start-browser", response_model=ApplicationRead)
async def start_browser(application_id: int, db: Session = Depends(get_db)):
    application = _get_application_or_404(db, application_id)
    try:
        await application_service.start_browser(db, application)
    except browser_manager.BrowserLaunchError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc))
    db.refresh(application)
    return application


@applications_router.post("/{application_id}/analyze-page", response_model=PageAnalysisResponse)
async def analyze_page(application_id: int, db: Session = Depends(get_db)):
    application = _get_application_or_404(db, application_id)
    try:
        analysis = await application_service.analyze_page(db, application)
    except ApplicationInputError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc))
    return PageAnalysisResponse.model_validate(analysis, from_attributes=True)


@applications_router.post("/{application_id}/fill", response_model=FillResultResponse)
async def fill(application_id: int, db: Session = Depends(get_db)):
    application = _get_application_or_404(db, application_id)
    try:
        result = await application_service.fill(db, application)
    except ApplicationInputError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc))
    return FillResultResponse(
        filled=result["filled"], uploaded=result["uploaded"], needs_user_input=result["needs_user_input"],
    )


@applications_router.get("/{application_id}/review", response_model=ApplicationReviewResponse)
def get_review(application_id: int, db: Session = Depends(get_db)):
    application = _get_application_or_404(db, application_id)
    result = application_service.get_review(db, application)
    return ApplicationReviewResponse(
        application=result["application"], fields=result["fields"],
        warnings=result["warnings"], ready_for_submission=result["ready_for_submission"],
    )


@applications_router.post("/{application_id}/fields/{field_id}/input", response_model=ApplicationFieldRead)
async def provide_user_input(application_id: int, field_id: int, payload: UserInputRequest, db: Session = Depends(get_db)):
    application = _get_application_or_404(db, application_id)
    try:
        return await application_service.provide_user_input(db, application, field_id, payload.value)
    except ApplicationInputError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc))


@applications_router.post("/{application_id}/approve-submission", response_model=ApplicationRead)
def approve_submission(application_id: int, db: Session = Depends(get_db)):
    """The only way Application.submission_approved becomes True (spec
    section 26). Calling this alone never submits anything -- DRY_RUN and
    submission_guard.can_click_submit() are still checked at submit time."""

    application = _get_application_or_404(db, application_id)
    return application_service.approve_submission(db, application)


@applications_router.post("/{application_id}/submit", response_model=SubmitResultResponse)
async def submit(application_id: int, db: Session = Depends(get_db)):
    application = _get_application_or_404(db, application_id)
    try:
        result = await application_service.submit(db, application)
    except ApplicationInputError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc))

    settings = get_settings()
    return SubmitResultResponse(
        submitted=result.get("submitted", False),
        dry_run=settings.dry_run,
        reason=result.get("reason"),
        confirmation_reference=result.get("confirmation_reference"),
    )


@applications_router.post("/{application_id}/pause", response_model=ApplicationRead)
def pause(application_id: int, db: Session = Depends(get_db)):
    application = _get_application_or_404(db, application_id)
    return application_service.pause(db, application)


@applications_router.post("/{application_id}/resume", response_model=ApplicationRead)
def resume(application_id: int, db: Session = Depends(get_db)):
    application = _get_application_or_404(db, application_id)
    return application_service.resume(db, application)


@applications_router.post("/{application_id}/cancel", response_model=ApplicationRead)
async def cancel(application_id: int, db: Session = Depends(get_db)):
    application = _get_application_or_404(db, application_id)
    return await application_service.cancel(db, application)
