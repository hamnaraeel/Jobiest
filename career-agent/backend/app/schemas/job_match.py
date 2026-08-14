from datetime import datetime

from pydantic import BaseModel, Field

from app.models.enums import Recommendation


class RequirementMatchDetail(BaseModel):
    requirement: str
    category: str
    importance: str
    required: bool
    status: str
    evidence: list[str] = Field(default_factory=list)
    reason: str | None = None


class JobSummaryRef(BaseModel):
    title: str | None
    company: str | None
    location: str | None


class JobMatchRead(BaseModel):
    job: JobSummaryRef
    score: int
    recommendation: Recommendation
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    matched_requirements: list[RequirementMatchDetail] = Field(default_factory=list)
    partial_requirements: list[RequirementMatchDetail] = Field(default_factory=list)
    missing_requirements: list[RequirementMatchDetail] = Field(default_factory=list)
    unknown_requirements: list[RequirementMatchDetail] = Field(default_factory=list)
    critical_gaps: list[str] = Field(default_factory=list)
    summary: str | None
    created_at: datetime
    updated_at: datetime
