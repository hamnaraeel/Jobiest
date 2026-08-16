"""Step 6: the central job-search tracking layer. Owns application
status transitions (never overwriting history), the unified timeline,
the application-readiness check, the post-submission material snapshot,
and job-level duplicate detection.

This module never submits, fills, or automates anything -- that is
entirely Step 5's job. Step 6 only records and organizes what has
already happened.
"""

import logging
import re
from dataclasses import dataclass, field
from datetime import date as date_cls
from datetime import datetime, time, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.browser import submission_guard
from app.models.application import Application
from app.models.application_field import ApplicationField
from app.models.application_followup import ApplicationFollowUp
from app.models.application_status_history import ApplicationStatusHistory
from app.models.enums import FollowUpStatus, InterviewStatus, RequirementCategory
from app.models.interview import Interview
from app.models.enums import ApplicationFieldStatus, ApplicationMaterialStatus, ApplicationStatus
from app.models.job import Job

logger = logging.getLogger("app.tracking_service")


class TrackingInputError(ValueError):
    pass


# --- Status transitions -------------------------------------------------


def change_application_status(
    db: Session, application: Application, new_status: ApplicationStatus,
    reason: str | None = None, source: str = "user",
) -> Application:
    """The only way Application.status is ever allowed to change, from
    either a manual PATCH or Step 5's own confirmed-submission path.
    Every transition is appended to ApplicationStatusHistory -- nothing
    is ever overwritten, so the full submitted -> under_review ->
    interview -> ... chain stays inspectable (spec sections 5-7)."""

    old_status = application.status
    db.add(ApplicationStatusHistory(
        application_id=application.id, old_status=old_status, new_status=new_status,
        reason=reason, source=source,
    ))
    application.status = new_status
    db.commit()
    db.refresh(application)
    logger.info("application id=%s status %s -> %s (source=%s)", application.id, old_status.value, new_status.value, source)
    return application


def mark_submitted(db: Session, application: Application, confirmation_reference: str | None) -> Application:
    """Called by Step 5 only after a submission is actually confirmed
    (never speculatively) -- spec section 5: "Step 5 should automatically
    update the status to submitted only after successful submission is
    confirmed." Also freezes the material snapshot (spec section 22)."""

    application.submitted_at = datetime.now(timezone.utc)
    application.confirmation_reference = confirmation_reference
    change_application_status(db, application, ApplicationStatus.SUBMITTED, reason="Submission confirmed.", source="system")
    application.material_snapshot = build_material_snapshot(db, application)
    db.commit()
    db.refresh(application)
    return application


# --- Material snapshot ---------------------------------------------------


def build_material_snapshot(db: Session, application: Application) -> dict:
    """Everything that mattered at submission time, frozen -- the job
    posting, CV, or cover letter can all change later, but a submitted
    application must stay historically accurate to what was actually
    sent (spec section 22)."""

    job = application.job
    cv = application.cv_version
    cover_letter = application.cover_letter
    match = job.match if job else None

    fields = db.execute(
        select(ApplicationField).where(ApplicationField.application_id == application.id)
    ).scalars().all()

    return {
        "snapshotted_at": datetime.now(timezone.utc).isoformat(),
        "job": {
            "title": job.title, "company": job.company, "description": job.description, "url": job.url,
        } if job else None,
        "application_url": application.application_url,
        "match_score": match.overall_score if match else None,
        "match_algorithm_version": match.algorithm_version if match else None,
        "cv_version": {
            "id": cv.id, "version_name": cv.version_name, "version_number": cv.version_number,
            "summary": cv.summary, "skills": cv.skills, "experience": cv.experience,
            "projects": cv.projects, "education": cv.education,
        } if cv else None,
        "cover_letter": {
            "id": cover_letter.id, "version_name": cover_letter.version_name,
            "version_number": cover_letter.version_number, "content": cover_letter.content,
        } if cover_letter else None,
        "fields": [
            {"label": f.label, "field_identifier": f.field_identifier, "final_value": f.final_value, "mapped_source": f.mapped_source}
            for f in fields
        ],
    }


# --- Readiness -------------------------------------------------------------


def check_readiness(db: Session, application: Application, requires_cover_letter: bool = False) -> dict:
    """GET /applications/{id}/readiness (spec section 48). Reuses Step 5's
    own submission_guard checks (the single source of truth for "is this
    actually ready to submit") and additionally reports each check as an
    individual named boolean, as the spec's response shape requires."""

    fields = db.execute(select(ApplicationField).where(ApplicationField.application_id == application.id)).scalars().all()
    check = submission_guard.check_ready_for_submission(
        application, fields, application.cv_version, application.cover_letter, requires_cover_letter=requires_cover_letter,
    )

    unresolved_required = [
        f for f in fields
        if f.required and f.status not in (ApplicationFieldStatus.FILLED, ApplicationFieldStatus.SKIPPED)
    ]
    cv_approved = application.cv_version is not None and application.cv_version.status == ApplicationMaterialStatus.APPROVED
    cover_letter_approved = application.cover_letter is None or application.cover_letter.status == ApplicationMaterialStatus.APPROVED
    if requires_cover_letter and application.cover_letter is None:
        cover_letter_approved = False

    return {
        "ready": check.ready,
        "checks": {
            "job_valid": application.job is not None,
            "cv_approved": cv_approved,
            "cover_letter_approved": cover_letter_approved,
            "required_answers_complete": not unresolved_required,
            "application_url_valid": bool(application.application_url),
        },
        "warnings": check.warnings,
    }


# --- Timeline ----------------------------------------------------------


@dataclass
class TimelineEntry:
    timestamp: datetime
    entry_type: str
    description: str
    metadata: dict = field(default_factory=dict)


def build_timeline(application: Application) -> list[TimelineEntry]:
    """Merges job events, application events, status changes, notes,
    interviews, and follow-ups into one chronological view (spec
    section 8)."""

    entries: list[TimelineEntry] = []

    job = application.job
    if job is not None:
        if job.created_at:
            entries.append(TimelineEntry(job.created_at, "job", "Job discovered"))
        if job.extracted_at:
            entries.append(TimelineEntry(job.extracted_at, "job", "Job analyzed"))
        if job.match is not None:
            entries.append(TimelineEntry(
                job.match.created_at, "job", f"Job matched (score: {job.match.overall_score}%)",
                {"score": job.match.overall_score},
            ))

    for event in application.events:
        entries.append(TimelineEntry(event.timestamp, "event", event.description, {"event_type": event.event_type.value, **(event.event_metadata or {})}))

    for history in application.status_history:
        old = history.old_status.value if history.old_status else "none"
        description = f"Status changed: {old} -> {history.new_status.value}"
        if history.reason:
            description += f" ({history.reason})"
        entries.append(TimelineEntry(
            history.created_at, "status_change", description,
            {"old_status": old, "new_status": history.new_status.value, "reason": history.reason, "source": history.source},
        ))

    for note in application.notes:
        entries.append(TimelineEntry(note.created_at, "note", note.content, {"note_type": note.note_type.value}))

    for interview in application.interviews:
        timestamp = interview.scheduled_at or interview.created_at
        description = f"{interview.type.value.replace('_', ' ').title()} interview"
        if interview.interviewer:
            description += f" with {interview.interviewer}"
        entries.append(TimelineEntry(timestamp, "interview", description, {"status": interview.status.value, "interview_id": interview.id}))

    for followup in application.followups:
        due = datetime.combine(followup.due_date, time.min, tzinfo=timezone.utc)
        description = followup.subject or followup.type.value.replace("_", " ").title()
        entries.append(TimelineEntry(due, "followup", f"Follow-up due: {description}", {"status": followup.status.value, "followup_id": followup.id}))

    for offer in application.offers:
        description = f"Offer received: {offer.role or 'role'} at {offer.company or 'company'}"
        entries.append(TimelineEntry(offer.created_at, "offer", description, {"status": offer.status.value, "offer_id": offer.id}))

    entries.sort(key=lambda e: e.timestamp)
    return entries


# --- Duplicate detection --------------------------------------------------


def normalize_title(title: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (title or "").lower()).strip()


def find_possible_duplicate_jobs(db: Session, job: Job) -> list[Job]:
    """Possible-duplicate check by exact job URL, canonical URL, external
    job id, or company + normalized title (spec section 25). Never blocks
    anything by itself -- callers surface this as a warning and let the
    user decide."""

    found: dict[int, Job] = {}

    def _add_all(candidates):
        for candidate in candidates:
            if candidate.id != job.id:
                found[candidate.id] = candidate

    if job.canonical_url:
        _add_all(db.execute(select(Job).where(Job.canonical_url == job.canonical_url)).scalars().all())
    if job.url:
        _add_all(db.execute(select(Job).where(Job.url == job.url)).scalars().all())
    if job.external_job_id:
        _add_all(db.execute(select(Job).where(Job.external_job_id == job.external_job_id)).scalars().all())
    if job.company and job.title:
        norm_title = normalize_title(job.title)
        same_company = db.execute(select(Job).where(Job.company == job.company)).scalars().all()
        _add_all([j for j in same_company if normalize_title(j.title) == norm_title])

    return list(found.values())


# --- Interview context (spec section 57) --------------------------------


def build_interview_context(db: Session, application: Application) -> dict:
    """Everything a future interview-prep step (Step 7) would need,
    assembled from data that already exists -- no new AI call, no
    invented content."""

    job = application.job
    cv = application.cv_version
    cover_letter = application.cover_letter

    required_skills = []
    if job is not None:
        required_skills = [
            r.skill_name or r.requirement_text for r in job.requirements
            if r.category == RequirementCategory.TECHNICAL_SKILL
        ]
    matched_skills = []
    if job is not None and job.match is not None:
        matched_skills = [m.get("requirement") for m in job.match.matched_requirements]

    projects_used = [p.get("name") for p in cv.projects] if cv else []
    experience_used = [f"{e.get('role', '')} at {e.get('company', '')}".strip() for e in cv.experience] if cv else []

    return {
        "job_title": job.title if job else None,
        "company": job.company if job else None,
        "job_description": job.description if job else None,
        "required_skills": required_skills,
        "matched_skills": matched_skills,
        "cv_version": cv.version_name if cv else None,
        "projects_used": projects_used,
        "experience_used": experience_used,
        "cover_letter": cover_letter.content if cover_letter else None,
        "notes": [n.content for n in application.notes],
    }


# --- Notifications / calendar --------------------------------------------


def upcoming_notifications(db: Session, within_days: int = 14) -> list[dict]:
    """GET /notifications/upcoming (spec section 58) -- follow-ups due,
    interviews upcoming, deadlines approaching. Never sends anything;
    purely a read-only surface for the user to act on."""

    notifications: list[dict] = []
    cutoff_date = (datetime.now(timezone.utc) + timedelta(days=within_days)).date()

    followups = db.execute(
        select(ApplicationFollowUp).where(
            ApplicationFollowUp.status == FollowUpStatus.PENDING, ApplicationFollowUp.due_date <= cutoff_date,
        )
    ).scalars().all()
    for f in followups:
        notifications.append({
            "type": "followup", "due_date": f.due_date, "application_id": f.application_id,
            "message": f"Follow up: {f.subject or f.type.value}",
        })

    cutoff_dt = datetime.now(timezone.utc) + timedelta(days=within_days)
    interviews = db.execute(
        select(Interview).where(
            Interview.status == InterviewStatus.SCHEDULED, Interview.scheduled_at.isnot(None),
            Interview.scheduled_at <= cutoff_dt,
        )
    ).scalars().all()
    for i in interviews:
        notifications.append({
            "type": "interview", "due_date": i.scheduled_at.date() if i.scheduled_at else None,
            "application_id": i.application_id, "message": f"Upcoming {i.type.value.replace('_', ' ')} interview",
        })

    jobs = db.execute(
        select(Job).where(Job.application_deadline.isnot(None), Job.application_deadline <= cutoff_date)
    ).scalars().all()
    for j in jobs:
        notifications.append({
            "type": "deadline", "due_date": j.application_deadline, "job_id": j.id,
            "message": f"Application deadline approaching: {j.title or 'job'} at {j.company or 'company'}",
        })

    notifications.sort(key=lambda n: n["due_date"] or date_cls.max)
    return notifications
