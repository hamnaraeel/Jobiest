"""Free-form notes at the application and job level (spec sections 15-16).
Never modifies the Career Profile or any other record -- purely an
observation the user records for themselves."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.browser.adapters.generic import log_event
from app.models.application import Application
from app.models.application_note import ApplicationNote
from app.models.enums import ApplicationEventType, ApplicationNoteType
from app.models.job import Job
from app.models.job_note import JobNote


def add_application_note(db: Session, application: Application, content: str, note_type: ApplicationNoteType = ApplicationNoteType.GENERAL) -> ApplicationNote:
    note = ApplicationNote(application_id=application.id, content=content, note_type=note_type)
    db.add(note)
    db.commit()
    db.refresh(note)
    log_event(db, application, ApplicationEventType.NOTE_ADDED, f"Note added ({note_type.value}).", {"note_id": note.id})
    return note


def list_application_notes(db: Session, application_id: int) -> list[ApplicationNote]:
    return db.execute(select(ApplicationNote).where(ApplicationNote.application_id == application_id).order_by(ApplicationNote.created_at)).scalars().all()


def add_job_note(db: Session, job: Job, content: str) -> JobNote:
    note = JobNote(job_id=job.id, content=content)
    db.add(note)
    db.commit()
    db.refresh(note)
    return note


def list_job_notes(db: Session, job_id: int) -> list[JobNote]:
    return db.execute(select(JobNote).where(JobNote.job_id == job_id).order_by(JobNote.created_at)).scalars().all()
