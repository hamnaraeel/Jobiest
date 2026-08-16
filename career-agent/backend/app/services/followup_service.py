"""Follow-up reminders (spec sections 10-12). Purely a tracking/reminder
record -- nothing here ever sends a message, email, or notification on
its own. A suggested follow-up date is exactly that: a suggestion the
user must explicitly turn into a real ApplicationFollowUp row."""

import logging
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.browser.adapters.generic import log_event
from app.config import get_settings
from app.models.application import Application
from app.models.application_followup import ApplicationFollowUp
from app.models.enums import ApplicationEventType, FollowUpStatus, FollowUpType

logger = logging.getLogger("app.followup_service")


class FollowUpInputError(ValueError):
    pass


def suggested_followup_date(application: Application) -> date | None:
    """A pure suggestion, computed from settings.DEFAULT_FOLLOWUP_DAYS --
    never persisted or acted on unless the user explicitly creates a
    follow-up (spec section 12)."""

    if application.submitted_at is None:
        return None
    settings = get_settings()
    return (application.submitted_at + timedelta(days=settings.default_followup_days)).date()


def create_followup(
    db: Session, application: Application, due_date: date,
    type: FollowUpType = FollowUpType.CUSTOM, subject: str | None = None, notes: str | None = None,
) -> ApplicationFollowUp:
    followup = ApplicationFollowUp(
        application_id=application.id, due_date=due_date, type=type, subject=subject, notes=notes,
    )
    db.add(followup)
    db.commit()
    db.refresh(followup)
    log_event(db, application, ApplicationEventType.FOLLOW_UP, f"Follow-up created for {due_date.isoformat()}: {subject or type.value}", {"followup_id": followup.id})
    return followup


def list_followups(db: Session, application_id: int) -> list[ApplicationFollowUp]:
    return db.execute(
        select(ApplicationFollowUp).where(ApplicationFollowUp.application_id == application_id).order_by(ApplicationFollowUp.due_date)
    ).scalars().all()


def update_followup(
    db: Session, followup: ApplicationFollowUp, status: FollowUpStatus | None = None,
    due_date: date | None = None, subject: str | None = None, notes: str | None = None,
) -> ApplicationFollowUp:
    if status is not None:
        followup.status = status
        followup.completed_at = datetime.now(timezone.utc) if status == FollowUpStatus.COMPLETED else followup.completed_at
    if due_date is not None:
        followup.due_date = due_date
    if subject is not None:
        followup.subject = subject
    if notes is not None:
        followup.notes = notes
    db.commit()
    db.refresh(followup)
    return followup


def upcoming_followups(db: Session, within_days: int | None = None) -> list[ApplicationFollowUp]:
    """Pending follow-ups due today or overdue (and, if within_days is
    given, due within that window) -- used by GET /notifications/upcoming
    and GET /calendar/upcoming. Never sends anything; just surfaces the
    list for the user to act on (spec section 11)."""

    stmt = select(ApplicationFollowUp).where(ApplicationFollowUp.status == FollowUpStatus.PENDING)
    if within_days is not None:
        cutoff = (datetime.now(timezone.utc) + timedelta(days=within_days)).date()
        stmt = stmt.where(ApplicationFollowUp.due_date <= cutoff)
    return db.execute(stmt.order_by(ApplicationFollowUp.due_date)).scalars().all()
