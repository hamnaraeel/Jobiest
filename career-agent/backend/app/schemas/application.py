from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import (
    ApplicationEventType,
    ApplicationFieldStatus,
    ApplicationFieldType,
    ApplicationPlatform,
    ApplicationStatus,
    PriorityLevel,
    RejectionReason,
)


class ApplicationCreateRequest(BaseModel):
    application_url: str | None = Field(default=None, description="Defaults to the job's own URL if omitted.")
    cv_version_id: int | None = Field(default=None, description="Defaults to the latest approved CV for this job.")
    cover_letter_id: int | None = Field(default=None, description="Defaults to the latest approved cover letter for this job.")
    force: bool = Field(default=False, description="Create a new attempt even if one was already submitted for this job.")
    source: str | None = Field(default=None, description="Where this application was submitted from, e.g. LinkedIn, Indeed, referral.")


class ApplicationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    job_id: int
    cv_version_id: int | None
    cover_letter_id: int | None
    original_job_url: str | None
    application_url: str | None
    platform: ApplicationPlatform
    status: ApplicationStatus
    submission_approved: bool
    started_at: datetime | None
    submitted_at: datetime | None
    confirmation_reference: str | None
    priority: PriorityLevel
    tags: list[str] = Field(default_factory=list)
    source: str | None
    archived: bool
    material_snapshot: dict | None
    rejection_reason: RejectionReason | None
    rejection_reason_custom: str | None
    created_at: datetime
    updated_at: datetime


class ApplicationListResponse(BaseModel):
    items: list[ApplicationRead]
    total: int


class ApplicationEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: int
    application_id: int
    event_type: ApplicationEventType
    description: str
    timestamp: datetime
    metadata_: dict = Field(default_factory=dict, alias="event_metadata", serialization_alias="metadata")


class ApplicationFieldRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    application_id: int
    field_identifier: str
    label: str | None
    field_type: ApplicationFieldType
    page_url: str | None
    required: bool
    detected_value: str | None
    mapped_source: str | None
    proposed_value: str | None
    final_value: str | None
    status: ApplicationFieldStatus
    confidence: float | None
    user_review_required: bool


class UserInputRequest(BaseModel):
    value: str


class PageAnalysisResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    url: str
    title: str
    captcha_detected: bool
    captcha_indicator: str | None
    login_required: bool
    has_password_field: bool


class ApplicationReviewResponse(BaseModel):
    application: ApplicationRead
    fields: list[ApplicationFieldRead]
    warnings: list[str]
    ready_for_submission: bool


class FillResultResponse(BaseModel):
    filled: list[ApplicationFieldRead]
    uploaded: list[ApplicationFieldRead]
    needs_user_input: list[ApplicationFieldRead]


class SubmitResultResponse(BaseModel):
    submitted: bool
    dry_run: bool
    reason: str | None = None
    confirmation_reference: str | None = None
