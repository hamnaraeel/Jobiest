"""Interview tracking (spec section 13). Only ever stores what the user
actually supplies -- never assumes or invents interview details."""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.browser.adapters.generic import log_event
from app.models.application import Application
from app.models.enums import ApplicationEventType, InterviewStatus, InterviewType
from app.models.interview import Interview


def create_interview(
    db: Session, application: Application, type: InterviewType = InterviewType.OTHER,
    scheduled_at: datetime | None = None, duration_minutes: int | None = None, location: str | None = None,
    meeting_url: str | None = None, interviewer: str | None = None, notes: str | None = None,
) -> Interview:
    interview = Interview(
        application_id=application.id, type=type, scheduled_at=scheduled_at, duration_minutes=duration_minutes,
        location=location, meeting_url=meeting_url, interviewer=interviewer, notes=notes,
    )
    db.add(interview)
    db.commit()
    db.refresh(interview)
    when = scheduled_at.isoformat() if scheduled_at else "unscheduled"
    log_event(db, application, ApplicationEventType.INTERVIEW_SCHEDULED, f"{type.value.replace('_', ' ').title()} interview recorded ({when}).", {"interview_id": interview.id})
    return interview


def list_interviews(db: Session, application_id: int) -> list[Interview]:
    return db.execute(
        select(Interview).where(Interview.application_id == application_id).order_by(Interview.scheduled_at)
    ).scalars().all()


def update_interview(
    db: Session, interview: Interview, application: Application, status: InterviewStatus | None = None,
    notes: str | None = None, scheduled_at: datetime | None = None,
) -> Interview:
    if status is not None:
        interview.status = status
        if status == InterviewStatus.COMPLETED:
            log_event(db, application, ApplicationEventType.INTERVIEW_COMPLETED, f"{interview.type.value.replace('_', ' ').title()} interview completed.", {"interview_id": interview.id})
    if notes is not None:
        interview.notes = notes
    if scheduled_at is not None:
        interview.scheduled_at = scheduled_at
    db.commit()
    db.refresh(interview)
    return interview
