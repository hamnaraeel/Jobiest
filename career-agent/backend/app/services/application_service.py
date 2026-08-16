"""DB-level orchestration for the browser-assisted application workflow.
The actual Playwright mechanics live in app/browser/*; this module wires
them to the database (Application/ApplicationEvent/ApplicationField rows)
and enforces the workflow-level rules (duplicate detection, status
transitions, the explicit-approval requirement).
"""

import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.browser import browser_manager, form_filler
from app.browser.adapters.generic import log_event
from app.browser.platform_detector import detect_platform, get_adapter
from app.config import get_settings
from app.models.application import Application
from app.models.application_event import ApplicationEvent
from app.models.application_field import ApplicationField
from app.models.application_session import ApplicationSession
from app.models.cover_letter import CoverLetter
from app.models.cv_version import CVVersion
from app.models.enums import ApplicationEventType, ApplicationFieldStatus, ApplicationMaterialStatus, ApplicationStatus
from app.models.job import Job

logger = logging.getLogger("app.application_service")


class DuplicateApplicationError(ValueError):
    def __init__(self, existing_application_id: int):
        self.existing_application_id = existing_application_id
        super().__init__(
            f"An application for this job has already been submitted (application id={existing_application_id}). "
            f"Pass force=true to create a new attempt anyway."
        )


class ApplicationInputError(ValueError):
    pass


def _latest_approved_cv(db: Session, job_id: int) -> CVVersion | None:
    return db.execute(
        select(CVVersion).where(CVVersion.job_id == job_id, CVVersion.status == ApplicationMaterialStatus.APPROVED)
        .order_by(CVVersion.version_number.desc()).limit(1)
    ).scalar_one_or_none()


def _latest_approved_cover_letter(db: Session, job_id: int) -> CoverLetter | None:
    return db.execute(
        select(CoverLetter).where(CoverLetter.job_id == job_id, CoverLetter.status == ApplicationMaterialStatus.APPROVED)
        .order_by(CoverLetter.version_number.desc()).limit(1)
    ).scalar_one_or_none()


def create_application(
    db: Session, job: Job, application_url: str | None = None,
    cv_version_id: int | None = None, cover_letter_id: int | None = None, force: bool = False,
    source: str | None = None,
) -> Application:
    if not force:
        existing_submitted = db.execute(
            select(Application).where(Application.job_id == job.id, Application.status == ApplicationStatus.SUBMITTED)
        ).scalar_one_or_none()
        if existing_submitted:
            raise DuplicateApplicationError(existing_submitted.id)

    url = application_url or job.url
    if not url:
        raise ApplicationInputError("No application_url was given and the job has no URL on file.")

    cv_version = db.get(CVVersion, cv_version_id) if cv_version_id else _latest_approved_cv(db, job.id)
    cover_letter = db.get(CoverLetter, cover_letter_id) if cover_letter_id else _latest_approved_cover_letter(db, job.id)

    application = Application(
        job_id=job.id, cv_version_id=cv_version.id if cv_version else None,
        cover_letter_id=cover_letter.id if cover_letter else None,
        original_job_url=job.url, application_url=url,
        platform=detect_platform(url), status=ApplicationStatus.NOT_STARTED,
        source=source,
    )
    db.add(application)
    db.commit()
    db.refresh(application)
    log_event(db, application, ApplicationEventType.APPLICATION_CREATED, f"Application created for job_id={job.id}.")
    return application


async def start_browser(db: Session, application: Application) -> None:
    application.status = ApplicationStatus.PREPARING
    application.started_at = datetime.now(timezone.utc)
    db.commit()

    settings = get_settings()
    try:
        session = await browser_manager.start_session(application.id)
    except browser_manager.BrowserLaunchError as exc:
        application.status = ApplicationStatus.FAILED
        db.commit()
        log_event(db, application, ApplicationEventType.BLOCKED, f"Browser launch failed: {exc}")
        raise

    db.add(ApplicationSession(
        application_id=application.id, browser=settings.browser_type,
        started_at=datetime.now(timezone.utc), current_url=None,
    ))
    application.status = ApplicationStatus.BROWSER_OPEN
    db.commit()
    log_event(db, application, ApplicationEventType.BROWSER_OPENED, f"Browser opened ({settings.browser_type}, headless={settings.browser_headless}).")

    adapter = get_adapter(application.platform)
    await adapter.open(session.page, application)


def _require_session(application_id: int):
    session = browser_manager.get_session(application_id)
    if session is None:
        raise ApplicationInputError("No active browser session for this application. Call start-browser first.")
    return session


async def analyze_page(db: Session, application: Application):
    session = _require_session(application.id)
    application.status = ApplicationStatus.FILLING
    db.commit()
    adapter = get_adapter(application.platform)
    return await adapter.analyze_page(session.page, db, application)


async def fill(db: Session, application: Application) -> dict:
    session = _require_session(application.id)
    adapter = get_adapter(application.platform)
    filled = await adapter.fill_fields(session.page, db, application)
    uploaded = await adapter.upload_files(session.page, db, application)

    remaining_review = db.execute(
        select(ApplicationField).where(
            ApplicationField.application_id == application.id,
            ApplicationField.user_review_required.is_(True),
            ApplicationField.status.notin_([ApplicationFieldStatus.FILLED, ApplicationFieldStatus.SKIPPED]),
        )
    ).scalars().all()

    if remaining_review:
        application.status = ApplicationStatus.NEEDS_USER_INPUT
        db.commit()
        log_event(
            db, application, ApplicationEventType.USER_INPUT_REQUIRED,
            f"{len(remaining_review)} field(s) need user input before this can proceed.",
        )
    else:
        db.commit()

    return {"filled": filled, "uploaded": uploaded, "needs_user_input": remaining_review}


def get_review(db: Session, application: Application) -> dict:
    adapter = get_adapter(application.platform)
    result = adapter.prepare_review(db, application)
    return {
        "application": application,
        "job": application.job,
        "cv_version": application.cv_version,
        "cover_letter": application.cover_letter,
        "fields": result["fields"],
        "warnings": result["warnings"],
        "ready_for_submission": result["ready_for_submission"],
    }


async def provide_user_input(db: Session, application: Application, field_id: int, value: str) -> ApplicationField:
    """Stores a user-provided answer against this specific application's
    field only -- the Career Profile is never modified automatically (spec
    section 42). A future step could add an explicit opt-in "save as
    permanent preference" action; nothing does that implicitly here.

    Also writes the value into the live browser page immediately, if a
    session is open -- storing it in the database alone isn't enough: a
    required field left empty in the actual DOM makes the browser's own
    HTML5 validation block the real submit handler from ever firing later,
    so this can't be deferred to a later fill() call (fill() only
    re-attempts fields still in status=MAPPED, and this field is about to
    leave that status)."""

    field_row = db.get(ApplicationField, field_id)
    if field_row is None or field_row.application_id != application.id:
        raise ApplicationInputError(f"No field with id={field_id} on this application.")

    field_row.proposed_value = value
    field_row.mapped_source = "user_input"

    session = browser_manager.get_session(application.id)
    filled_in_browser = True
    if session is not None:
        filled_in_browser = await form_filler.fill_field(session.page, field_row)

    field_row.final_value = value if filled_in_browser else None
    field_row.status = ApplicationFieldStatus.FILLED if filled_in_browser else ApplicationFieldStatus.NEEDS_REVIEW
    field_row.user_review_required = not filled_in_browser
    db.commit()
    db.refresh(field_row)

    if filled_in_browser:
        log_event(db, application, ApplicationEventType.FIELD_FILLED, f"User-provided value stored for '{field_row.label or field_row.field_identifier}'.", {"field_id": field_row.id, "source": "user_input"})
    else:
        log_event(db, application, ApplicationEventType.BLOCKED, f"Could not write user-provided value into the browser for '{field_row.label or field_row.field_identifier}'.", {"field_id": field_row.id})
    return field_row


def approve_submission(db: Session, application: Application) -> Application:
    """The one and only way Application.submission_approved becomes True.
    This is an explicit, unambiguous user action -- not inferred from any
    other message or endpoint call (spec section 26)."""

    application.submission_approved = True
    application.status = ApplicationStatus.APPROVED_FOR_SUBMISSION
    db.commit()
    db.refresh(application)
    log_event(db, application, ApplicationEventType.SUBMISSION_APPROVED, "User explicitly approved submission.")
    return application


async def submit(db: Session, application: Application) -> dict:
    session = _require_session(application.id)
    adapter = get_adapter(application.platform)
    return await adapter.submit(session.page, db, application)


def pause(db: Session, application: Application) -> Application:
    application.status = ApplicationStatus.NEEDS_USER_INPUT
    db.commit()
    log_event(db, application, ApplicationEventType.USER_INPUT_REQUIRED, "Application paused by user request.")
    return application


def resume(db: Session, application: Application) -> Application:
    application.status = ApplicationStatus.FILLING
    db.commit()
    return application


async def cancel(db: Session, application: Application) -> Application:
    await browser_manager.close_session(application.id)
    application.status = ApplicationStatus.ABANDONED
    db.commit()
    log_event(db, application, ApplicationEventType.BLOCKED, "Application cancelled/abandoned by user.")
    return application
