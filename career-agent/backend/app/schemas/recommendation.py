from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import PriorityLevel, RecommendationStatus, RecommendationType


class RecommendationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    type: RecommendationType
    title: str
    description: str
    priority: PriorityLevel
    confidence: float
    confidence_reason: str
    evidence: dict = Field(default_factory=dict)
    action: str | None
    related_job_id: int | None
    related_application_id: int | None
    expires_at: datetime | None
    status: RecommendationStatus
    created_at: datetime
    updated_at: datetime


class RecommendationListResponse(BaseModel):
    items: list[RecommendationRead]
    total: int


class GoalUpdateRequest(BaseModel):
    target_roles: list[str] | None = None
    target_locations: list[str] | None = None
    remote_preference: str | None = None
    target_companies: list[str] | None = None
    minimum_match_score: int | None = None
    applications_per_week: int | None = None
    interviews_per_month: int | None = None
    salary_min: int | None = None
    salary_max: int | None = None
    salary_currency: str | None = None
    employment_types: list[str] | None = None


class GoalRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    target_roles: list[str] = Field(default_factory=list)
    target_locations: list[str] = Field(default_factory=list)
    remote_preference: str | None
    target_companies: list[str] = Field(default_factory=list)
    minimum_match_score: int | None
    applications_per_week: int | None
    interviews_per_month: int | None
    salary_min: int | None
    salary_max: int | None
    salary_currency: str | None
    employment_types: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class GoalProgressResponse(BaseModel):
    goal: GoalRead
    progress: dict


class RejectionReasonUpdateRequest(BaseModel):
    rejection_reason: str
    rejection_reason_custom: str | None = None
