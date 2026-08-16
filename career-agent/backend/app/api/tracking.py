"""Step 6: job-search tracking, analytics, and follow-up management.

Reuses Job/Application/JobMatch/CVVersion/CoverLetter from Steps 1-5
throughout -- this file only adds the tracking-specific endpoints
(status history, timeline, follow-ups, interviews, offers, notes, tags,
priority, search, analytics, export, notifications, calendar). Nothing
here submits or automates an application; that stays entirely in Step 5.
"""

import logging
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import PlainTextResponse
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.browser.adapters.generic import log_event
from app.db.database import get_db
from app.models.application import Application
from app.models.application_followup import ApplicationFollowUp
from app.models.enums import (
    ApplicationPlatform,
    ApplicationStatus,
    InterviewStatus,
    JobStatus,
    PriorityLevel,
    WorkplaceType,
)
from app.models.interview import Interview
from app.models.job import Job
from app.models.job_match import JobMatch
from app.models.offer import Offer
from app.schemas.analytics import (
    CVVersionAnalyticsResponse,
    DashboardResponse,
    OverviewResponse,
    PeriodAnalyticsResponse,
    SkillAnalyticsResponse,
)
from app.schemas.application import ApplicationListResponse, ApplicationRead
from app.schemas.job import JobListResponse, JobRead
from app.schemas.tracking import (
    ApplicationNoteCreateRequest,
    ApplicationNoteRead,
    ApplicationStatusHistoryRead,
    ApplicationStatusUpdateRequest,
    CalendarItem,
    DuplicateCheckResponse,
    DuplicateJobSummary,
    FollowUpCreateRequest,
    FollowUpRead,
    FollowUpUpdateRequest,
    InterviewContextResponse,
    InterviewCreateRequest,
    InterviewRead,
    InterviewUpdateRequest,
    JobNoteCreateRequest,
    JobNoteRead,
    JobStatusUpdateRequest,
    ManualEventCreateRequest,
    NotificationItem,
    OfferCreateRequest,
    OfferRead,
    OfferUpdateRequest,
    PriorityUpdateRequest,
    ReadinessResponse,
    SuggestedFollowUpResponse,
    TagsUpdateRequest,
    TimelineEntryRead,
    TimelineResponse,
)
from app.services import analytics_service, followup_service, interview_service, note_service, offer_service, tracking_service
from app.services.export_service import export_applications, to_csv, to_json

logger = logging.getLogger("app.api.tracking")

dashboard_router = APIRouter(tags=["tracking"])
jobs_tracking_router = APIRouter(prefix="/jobs", tags=["tracking"])
applications_tracking_router = APIRouter(prefix="/applications", tags=["tracking"])
followups_router = APIRouter(prefix="/followups", tags=["tracking"])
analytics_router = APIRouter(prefix="/analytics", tags=["tracking"])
notifications_router = APIRouter(prefix="/notifications", tags=["tracking"])
calendar_router = APIRouter(prefix="/calendar", tags=["tracking"])


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


def _priority_rank(column):
    return case(
        (column == PriorityLevel.CRITICAL, 4), (column == PriorityLevel.HIGH, 3),
        (column == PriorityLevel.MEDIUM, 2), (column == PriorityLevel.LOW, 1), else_=0,
    )


# --- Dashboard -----------------------------------------------------------


@dashboard_router.get("/dashboard", response_model=DashboardResponse)
def get_dashboard(db: Session = Depends(get_db)):
    return analytics_service.dashboard(db)


# --- Job search / archive / notes / tags / priority / duplicates -----------


@jobs_tracking_router.get("/search", response_model=JobListResponse)
def search_jobs(
    db: Session = Depends(get_db),
    company: str | None = None,
    role: str | None = Query(None, description="Matches job title"),
    status_filter: JobStatus | None = Query(None, alias="status"),
    priority: PriorityLevel | None = None,
    tag: str | None = None,
    source: str | None = None,
    min_match_score: int | None = Query(None, ge=0, le=100),
    location: str | None = None,
    remote: bool | None = Query(None, description="Filter to remote-only (workplace_type=remote) when true"),
    discovered_after: date | None = None,
    discovered_before: date | None = None,
    sort: str = Query("newest", pattern="^(newest|oldest|highest_match|lowest_match|deadline|priority)$"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    stmt = select(Job).outerjoin(JobMatch, JobMatch.job_id == Job.id)
    count_stmt = select(func.count(Job.id.distinct())).select_from(Job).outerjoin(JobMatch, JobMatch.job_id == Job.id)

    conditions = []
    if company:
        conditions.append(Job.company.ilike(f"%{company}%"))
    if role:
        conditions.append(Job.title.ilike(f"%{role}%"))
    if status_filter:
        conditions.append(Job.status == status_filter)
    if priority:
        conditions.append(Job.priority == priority)
    if tag:
        conditions.append(Job.tags.any(tag))
    if source:
        conditions.append(Job.source.ilike(f"%{source}%"))
    if min_match_score is not None:
        conditions.append(JobMatch.overall_score >= min_match_score)
    if location:
        conditions.append(Job.location.ilike(f"%{location}%"))
    if remote is True:
        conditions.append(Job.workplace_type == WorkplaceType.REMOTE)
    if discovered_after:
        conditions.append(Job.created_at >= discovered_after)
    if discovered_before:
        conditions.append(Job.created_at <= discovered_before)

    for condition in conditions:
        stmt = stmt.where(condition)
        count_stmt = count_stmt.where(condition)

    order = {
        "newest": Job.created_at.desc(), "oldest": Job.created_at.asc(),
        "highest_match": JobMatch.overall_score.desc(), "lowest_match": JobMatch.overall_score.asc(),
        "deadline": Job.application_deadline.asc().nulls_last(),
        "priority": _priority_rank(Job.priority).desc(),
    }[sort]

    total = db.execute(count_stmt).scalar_one()
    jobs = db.execute(stmt.order_by(order).limit(limit).offset(offset)).scalars().all()
    return JobListResponse(items=[JobRead.model_validate(j) for j in jobs], total=total, limit=limit, offset=offset)


@jobs_tracking_router.post("/{job_id}/archive", response_model=JobRead)
def archive_job(job_id: int, db: Session = Depends(get_db)):
    job = _get_job_or_404(db, job_id)
    job.status = JobStatus.ARCHIVED
    db.commit()
    db.refresh(job)
    return job


@jobs_tracking_router.patch("/{job_id}/status", response_model=JobRead)
def update_job_status(job_id: int, payload: JobStatusUpdateRequest, db: Session = Depends(get_db)):
    job = _get_job_or_404(db, job_id)
    job.status = payload.status
    db.commit()
    db.refresh(job)
    return job


@jobs_tracking_router.patch("/{job_id}/tags", response_model=JobRead)
def update_job_tags(job_id: int, payload: TagsUpdateRequest, db: Session = Depends(get_db)):
    job = _get_job_or_404(db, job_id)
    job.tags = payload.tags
    db.commit()
    db.refresh(job)
    return job


@jobs_tracking_router.patch("/{job_id}/priority", response_model=JobRead)
def update_job_priority(job_id: int, payload: PriorityUpdateRequest, db: Session = Depends(get_db)):
    job = _get_job_or_404(db, job_id)
    job.priority = payload.priority
    db.commit()
    db.refresh(job)
    return job


@jobs_tracking_router.get("/{job_id}/duplicates", response_model=DuplicateCheckResponse)
def get_job_duplicates(job_id: int, db: Session = Depends(get_db)):
    """Possible-duplicate check (spec section 25) -- never blocks
    anything, just surfaces candidates for the user to review."""

    job = _get_job_or_404(db, job_id)
    candidates = tracking_service.find_possible_duplicate_jobs(db, job)
    return DuplicateCheckResponse(
        possible_duplicate=bool(candidates),
        candidates=[DuplicateJobSummary(id=c.id, title=c.title, company=c.company, status=c.status.value, url=c.url) for c in candidates],
    )


@jobs_tracking_router.post("/{job_id}/notes", response_model=JobNoteRead, status_code=status.HTTP_201_CREATED)
def create_job_note(job_id: int, payload: JobNoteCreateRequest, db: Session = Depends(get_db)):
    job = _get_job_or_404(db, job_id)
    return note_service.add_job_note(db, job, payload.content)


@jobs_tracking_router.get("/{job_id}/notes", response_model=list[JobNoteRead])
def list_job_notes(job_id: int, db: Session = Depends(get_db)):
    _get_job_or_404(db, job_id)
    return note_service.list_job_notes(db, job_id)


# --- Application search / status / timeline / readiness / interview-context ---


@applications_tracking_router.get("/search", response_model=ApplicationListResponse)
def search_applications(
    db: Session = Depends(get_db),
    company: str | None = None,
    role: str | None = None,
    status_filter: ApplicationStatus | None = Query(None, alias="status"),
    platform: ApplicationPlatform | None = None,
    priority: PriorityLevel | None = None,
    min_match_score: int | None = Query(None, ge=0, le=100),
    submitted_after: date | None = None,
    submitted_before: date | None = None,
    include_archived: bool = False,
    sort: str = Query("newest", pattern="^(newest|oldest|highest_match|lowest_match|priority|latest_status_change)$"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    stmt = select(Application).join(Job, Application.job_id == Job.id).outerjoin(JobMatch, JobMatch.job_id == Job.id)
    count_stmt = (
        select(func.count(Application.id.distinct())).select_from(Application)
        .join(Job, Application.job_id == Job.id).outerjoin(JobMatch, JobMatch.job_id == Job.id)
    )

    conditions = []
    if not include_archived:
        conditions.append(Application.archived.is_(False))
    if company:
        conditions.append(Job.company.ilike(f"%{company}%"))
    if role:
        conditions.append(Job.title.ilike(f"%{role}%"))
    if status_filter:
        conditions.append(Application.status == status_filter)
    if platform:
        conditions.append(Application.platform == platform)
    if priority:
        conditions.append(Application.priority == priority)
    if min_match_score is not None:
        conditions.append(JobMatch.overall_score >= min_match_score)
    if submitted_after:
        conditions.append(Application.submitted_at >= submitted_after)
    if submitted_before:
        conditions.append(Application.submitted_at <= submitted_before)

    for condition in conditions:
        stmt = stmt.where(condition)
        count_stmt = count_stmt.where(condition)

    order = {
        "newest": Application.created_at.desc(), "oldest": Application.created_at.asc(),
        "highest_match": JobMatch.overall_score.desc(), "lowest_match": JobMatch.overall_score.asc(),
        "priority": _priority_rank(Application.priority).desc(),
        "latest_status_change": Application.updated_at.desc(),
    }[sort]

    total = db.execute(count_stmt).scalar_one()
    applications = db.execute(stmt.order_by(order).limit(limit).offset(offset)).scalars().all()
    return ApplicationListResponse(items=[ApplicationRead.model_validate(a) for a in applications], total=total)


@applications_tracking_router.get("/{application_id}/timeline", response_model=TimelineResponse)
def get_timeline(application_id: int, db: Session = Depends(get_db)):
    application = _get_application_or_404(db, application_id)
    entries = tracking_service.build_timeline(application)
    return TimelineResponse(application_id=application_id, entries=[
        TimelineEntryRead(timestamp=e.timestamp, entry_type=e.entry_type, description=e.description, metadata=e.metadata)
        for e in entries
    ])


@applications_tracking_router.get("/{application_id}/readiness", response_model=ReadinessResponse)
def get_readiness(application_id: int, db: Session = Depends(get_db)):
    application = _get_application_or_404(db, application_id)
    return tracking_service.check_readiness(db, application)


@applications_tracking_router.get("/{application_id}/interview-context", response_model=InterviewContextResponse)
def get_interview_context(application_id: int, db: Session = Depends(get_db)):
    application = _get_application_or_404(db, application_id)
    return tracking_service.build_interview_context(db, application)


@applications_tracking_router.patch("/{application_id}/status", response_model=ApplicationRead)
def update_application_status(application_id: int, payload: ApplicationStatusUpdateRequest, db: Session = Depends(get_db)):
    application = _get_application_or_404(db, application_id)
    return tracking_service.change_application_status(db, application, payload.status, reason=payload.reason, source="user")


@applications_tracking_router.get("/{application_id}/status-history", response_model=list[ApplicationStatusHistoryRead])
def get_status_history(application_id: int, db: Session = Depends(get_db)):
    application = _get_application_or_404(db, application_id)
    return application.status_history


@applications_tracking_router.post("/{application_id}/events", status_code=status.HTTP_201_CREATED)
def create_manual_event(application_id: int, payload: ManualEventCreateRequest, db: Session = Depends(get_db)):
    application = _get_application_or_404(db, application_id)
    log_event(db, application, payload.event_type, payload.description, payload.metadata)
    return {"status": "recorded"}


@applications_tracking_router.post("/{application_id}/archive", response_model=ApplicationRead)
def archive_application(application_id: int, db: Session = Depends(get_db)):
    application = _get_application_or_404(db, application_id)
    application.archived = True
    db.commit()
    db.refresh(application)
    return application


@applications_tracking_router.patch("/{application_id}/tags", response_model=ApplicationRead)
def update_application_tags(application_id: int, payload: TagsUpdateRequest, db: Session = Depends(get_db)):
    application = _get_application_or_404(db, application_id)
    application.tags = payload.tags
    db.commit()
    db.refresh(application)
    return application


@applications_tracking_router.patch("/{application_id}/priority", response_model=ApplicationRead)
def update_application_priority(application_id: int, payload: PriorityUpdateRequest, db: Session = Depends(get_db)):
    application = _get_application_or_404(db, application_id)
    application.priority = payload.priority
    db.commit()
    db.refresh(application)
    return application


# --- Interviews ------------------------------------------------------------


@applications_tracking_router.post("/{application_id}/interviews", response_model=InterviewRead, status_code=status.HTTP_201_CREATED)
def create_interview(application_id: int, payload: InterviewCreateRequest, db: Session = Depends(get_db)):
    application = _get_application_or_404(db, application_id)
    return interview_service.create_interview(
        db, application, type=payload.type, scheduled_at=payload.scheduled_at, duration_minutes=payload.duration_minutes,
        location=payload.location, meeting_url=payload.meeting_url, interviewer=payload.interviewer, notes=payload.notes,
    )


@applications_tracking_router.get("/{application_id}/interviews", response_model=list[InterviewRead])
def list_interviews(application_id: int, db: Session = Depends(get_db)):
    _get_application_or_404(db, application_id)
    return interview_service.list_interviews(db, application_id)


@applications_tracking_router.patch("/{application_id}/interviews/{interview_id}", response_model=InterviewRead)
def update_interview(application_id: int, interview_id: int, payload: InterviewUpdateRequest, db: Session = Depends(get_db)):
    application = _get_application_or_404(db, application_id)
    interview = db.get(Interview, interview_id)
    if interview is None or interview.application_id != application_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No interview with id={interview_id} on this application.")
    return interview_service.update_interview(db, interview, application, status=payload.status, notes=payload.notes, scheduled_at=payload.scheduled_at)


# --- Follow-ups --------------------------------------------------------


@applications_tracking_router.get("/{application_id}/followups/suggested", response_model=SuggestedFollowUpResponse)
def get_suggested_followup(application_id: int, db: Session = Depends(get_db)):
    application = _get_application_or_404(db, application_id)
    from app.config import get_settings

    return SuggestedFollowUpResponse(
        suggested_due_date=followup_service.suggested_followup_date(application),
        default_followup_days=get_settings().default_followup_days,
    )


@applications_tracking_router.post("/{application_id}/followups", response_model=FollowUpRead, status_code=status.HTTP_201_CREATED)
def create_followup(application_id: int, payload: FollowUpCreateRequest, db: Session = Depends(get_db)):
    application = _get_application_or_404(db, application_id)
    return followup_service.create_followup(db, application, payload.due_date, type=payload.type, subject=payload.subject, notes=payload.notes)


@applications_tracking_router.get("/{application_id}/followups", response_model=list[FollowUpRead])
def list_followups(application_id: int, db: Session = Depends(get_db)):
    _get_application_or_404(db, application_id)
    return followup_service.list_followups(db, application_id)


@followups_router.patch("/{followup_id}", response_model=FollowUpRead)
def update_followup(followup_id: int, payload: FollowUpUpdateRequest, db: Session = Depends(get_db)):
    followup = db.get(ApplicationFollowUp, followup_id)
    if followup is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No follow-up with id={followup_id}")
    return followup_service.update_followup(db, followup, status=payload.status, due_date=payload.due_date, subject=payload.subject, notes=payload.notes)


# --- Offers ----------------------------------------------------------------


@applications_tracking_router.post("/{application_id}/offers", response_model=OfferRead, status_code=status.HTTP_201_CREATED)
def create_offer(application_id: int, payload: OfferCreateRequest, db: Session = Depends(get_db)):
    application = _get_application_or_404(db, application_id)
    return offer_service.create_offer(
        db, application, company=payload.company, role=payload.role, salary=payload.salary, currency=payload.currency,
        employment_type=payload.employment_type, location=payload.location, start_date=payload.start_date, notes=payload.notes,
    )


@applications_tracking_router.get("/{application_id}/offers", response_model=list[OfferRead])
def list_offers(application_id: int, db: Session = Depends(get_db)):
    _get_application_or_404(db, application_id)
    return offer_service.list_offers(db, application_id)


@applications_tracking_router.patch("/{application_id}/offers/{offer_id}", response_model=OfferRead)
def update_offer(application_id: int, offer_id: int, payload: OfferUpdateRequest, db: Session = Depends(get_db)):
    _get_application_or_404(db, application_id)
    offer = db.get(Offer, offer_id)
    if offer is None or offer.application_id != application_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No offer with id={offer_id} on this application.")
    return offer_service.update_offer(db, offer, status=payload.status, notes=payload.notes)


# --- Notes ---------------------------------------------------------------


@applications_tracking_router.post("/{application_id}/notes", response_model=ApplicationNoteRead, status_code=status.HTTP_201_CREATED)
def create_application_note(application_id: int, payload: ApplicationNoteCreateRequest, db: Session = Depends(get_db)):
    application = _get_application_or_404(db, application_id)
    return note_service.add_application_note(db, application, payload.content, note_type=payload.note_type)


@applications_tracking_router.get("/{application_id}/notes", response_model=list[ApplicationNoteRead])
def list_application_notes(application_id: int, db: Session = Depends(get_db)):
    _get_application_or_404(db, application_id)
    return note_service.list_application_notes(db, application_id)


# --- Export ----------------------------------------------------------------


@applications_tracking_router.get("/export")
def export(format: str = Query("csv", pattern="^(csv|json)$"), include_archived: bool = False, db: Session = Depends(get_db)):
    rows = export_applications(db, include_archived=include_archived)
    if format == "csv":
        return PlainTextResponse(to_csv(rows), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=applications.csv"})
    return PlainTextResponse(to_json(rows), media_type="application/json", headers={"Content-Disposition": "attachment; filename=applications.json"})


# --- Analytics ---------------------------------------------------------


@analytics_router.get("/overview", response_model=OverviewResponse)
def get_overview(db: Session = Depends(get_db)):
    return analytics_service.overview(db)


@analytics_router.get("/status")
def get_status_breakdown(db: Session = Depends(get_db)):
    return analytics_service.status_breakdown(db)


@analytics_router.get("/companies")
def get_company_analytics(db: Session = Depends(get_db)):
    return analytics_service.company_analytics(db)


@analytics_router.get("/roles")
def get_role_analytics(db: Session = Depends(get_db)):
    return analytics_service.role_analytics(db)


@analytics_router.get("/skills", response_model=SkillAnalyticsResponse)
def get_skill_analytics(db: Session = Depends(get_db)):
    return analytics_service.skill_analytics(db)


@analytics_router.get("/sources")
def get_source_analytics(db: Session = Depends(get_db)):
    return analytics_service.source_analytics(db)


@analytics_router.get("/match-scores")
def get_match_score_analysis(db: Session = Depends(get_db)):
    return analytics_service.match_score_analysis(db)


@analytics_router.get("/cv-versions", response_model=CVVersionAnalyticsResponse)
def get_cv_version_analytics(db: Session = Depends(get_db)):
    return analytics_service.cv_version_analytics(db)


@analytics_router.get("/weekly", response_model=PeriodAnalyticsResponse)
def get_weekly_analytics(reference: date | None = None, db: Session = Depends(get_db)):
    return analytics_service.weekly_analytics(db, reference=reference)


@analytics_router.get("/monthly", response_model=PeriodAnalyticsResponse)
def get_monthly_analytics(reference: date | None = None, db: Session = Depends(get_db)):
    return analytics_service.monthly_analytics(db, reference=reference)


# --- Notifications / calendar --------------------------------------------


@notifications_router.get("/upcoming", response_model=list[NotificationItem])
def get_upcoming_notifications(within_days: int = Query(14, ge=1, le=90), db: Session = Depends(get_db)):
    return tracking_service.upcoming_notifications(db, within_days=within_days)


@calendar_router.get("/upcoming", response_model=list[CalendarItem])
def get_upcoming_calendar(within_days: int = Query(30, ge=1, le=180), db: Session = Depends(get_db)):
    items: list[CalendarItem] = []

    followups = followup_service.upcoming_followups(db, within_days=within_days)
    for f in followups:
        items.append(CalendarItem(
            type="followup", date=datetime.combine(f.due_date, datetime.min.time(), tzinfo=timezone.utc),
            application_id=f.application_id, message=f"Follow-up: {f.subject or f.type.value}",
        ))

    interviews = db.execute(
        select(Interview).where(Interview.status == InterviewStatus.SCHEDULED, Interview.scheduled_at.isnot(None))
    ).scalars().all()
    for i in interviews:
        items.append(CalendarItem(
            type="interview", date=i.scheduled_at, application_id=i.application_id,
            message=f"{i.type.value.replace('_', ' ').title()} interview",
        ))

    jobs = db.execute(select(Job).where(Job.application_deadline.isnot(None))).scalars().all()
    for j in jobs:
        items.append(CalendarItem(
            type="deadline", date=datetime.combine(j.application_deadline, datetime.min.time(), tzinfo=timezone.utc),
            message=f"Application deadline: {j.title or 'job'} at {j.company or 'company'}",
        ))

    items.sort(key=lambda x: x.date)
    return items
