from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import (
    ApplicationEventType,
    ApplicationNoteType,
    ApplicationStatus,
    FollowUpStatus,
    FollowUpType,
    InterviewStatus,
    InterviewType,
    JobStatus,
    OfferStatus,
    PriorityLevel,
)


class ManualEventCreateRequest(BaseModel):
    event_type: ApplicationEventType
    description: str
    metadata: dict = Field(default_factory=dict)


class JobStatusUpdateRequest(BaseModel):
    status: JobStatus


# --- Status history / manual status update ----------------------------------


class ApplicationStatusUpdateRequest(BaseModel):
    status: ApplicationStatus
    reason: str | None = None


class ApplicationStatusHistoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    application_id: int
    old_status: ApplicationStatus | None
    new_status: ApplicationStatus
    reason: str | None
    source: str
    created_at: datetime


# --- Follow-ups --------------------------------------------------------


class FollowUpCreateRequest(BaseModel):
    due_date: date
    type: FollowUpType = FollowUpType.CUSTOM
    subject: str | None = None
    notes: str | None = None


class FollowUpUpdateRequest(BaseModel):
    status: FollowUpStatus | None = None
    due_date: date | None = None
    subject: str | None = None
    notes: str | None = None


class FollowUpRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    application_id: int
    due_date: date
    type: FollowUpType
    subject: str | None
    notes: str | None
    status: FollowUpStatus
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class SuggestedFollowUpResponse(BaseModel):
    suggested_due_date: date | None
    default_followup_days: int


# --- Interviews --------------------------------------------------------


class InterviewCreateRequest(BaseModel):
    type: InterviewType = InterviewType.OTHER
    scheduled_at: datetime | None = None
    duration_minutes: int | None = None
    location: str | None = None
    meeting_url: str | None = None
    interviewer: str | None = None
    notes: str | None = None


class InterviewUpdateRequest(BaseModel):
    status: InterviewStatus | None = None
    notes: str | None = None
    scheduled_at: datetime | None = None


class InterviewRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    application_id: int
    type: InterviewType
    scheduled_at: datetime | None
    duration_minutes: int | None
    location: str | None
    meeting_url: str | None
    interviewer: str | None
    notes: str | None
    status: InterviewStatus
    created_at: datetime
    updated_at: datetime


# --- Offers --------------------------------------------------------------


class OfferCreateRequest(BaseModel):
    company: str | None = None
    role: str | None = None
    salary: int | None = None
    currency: str | None = None
    employment_type: str | None = None
    location: str | None = None
    start_date: date | None = None
    notes: str | None = None


class OfferUpdateRequest(BaseModel):
    status: OfferStatus | None = None
    notes: str | None = None


class OfferRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    application_id: int
    company: str | None
    role: str | None
    salary: int | None
    currency: str | None
    employment_type: str | None
    location: str | None
    start_date: date | None
    notes: str | None
    status: OfferStatus
    created_at: datetime
    updated_at: datetime


# --- Notes ---------------------------------------------------------------


class ApplicationNoteCreateRequest(BaseModel):
    content: str
    note_type: ApplicationNoteType = ApplicationNoteType.GENERAL


class ApplicationNoteRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    application_id: int
    content: str
    note_type: ApplicationNoteType
    created_at: datetime
    updated_at: datetime


class JobNoteCreateRequest(BaseModel):
    content: str


class JobNoteRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    job_id: int
    content: str
    created_at: datetime
    updated_at: datetime


# --- Tags / priority -------------------------------------------------------


class TagsUpdateRequest(BaseModel):
    tags: list[str]


class PriorityUpdateRequest(BaseModel):
    priority: PriorityLevel


# --- Timeline --------------------------------------------------------------


class TimelineEntryRead(BaseModel):
    timestamp: datetime
    entry_type: str
    description: str
    metadata: dict = Field(default_factory=dict)


class TimelineResponse(BaseModel):
    application_id: int
    entries: list[TimelineEntryRead]


# --- Readiness ---------------------------------------------------------


class ReadinessChecks(BaseModel):
    job_valid: bool
    cv_approved: bool
    cover_letter_approved: bool
    required_answers_complete: bool
    application_url_valid: bool


class ReadinessResponse(BaseModel):
    ready: bool
    checks: ReadinessChecks
    warnings: list[str]


# --- Interview context (spec section 57) ------------------------------


class InterviewContextResponse(BaseModel):
    job_title: str | None
    company: str | None
    job_description: str | None
    required_skills: list[str]
    matched_skills: list[str]
    cv_version: str | None
    projects_used: list[str]
    experience_used: list[str]
    cover_letter: str | None
    notes: list[str]


# --- Notifications / calendar ----------------------------------------


class NotificationItem(BaseModel):
    type: str
    due_date: date | None = None
    application_id: int | None = None
    job_id: int | None = None
    message: str


class CalendarItem(BaseModel):
    type: str
    date: datetime
    application_id: int | None = None
    message: str


# --- Duplicate detection -------------------------------------------------


class DuplicateJobSummary(BaseModel):
    id: int
    title: str | None
    company: str | None
    status: str
    url: str | None


class DuplicateCheckResponse(BaseModel):
    possible_duplicate: bool
    candidates: list[DuplicateJobSummary]
