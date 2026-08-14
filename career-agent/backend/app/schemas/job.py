from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.enums import JobEmploymentType, JobStatus, WorkplaceType


class JobCreateRequest(BaseModel):
    url: str | None = None
    description: str | None = None

    @model_validator(mode="after")
    def _require_at_least_one(self):
        if not (self.url or "").strip() and not (self.description or "").strip():
            raise ValueError("Provide a url, a description, or both.")
        return self


class JobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str | None
    company: str | None
    location: str | None
    employment_type: JobEmploymentType | None
    workplace_type: WorkplaceType | None
    url: str | None
    source: str | None
    description: str | None
    summary: str | None
    keywords: list[str] = Field(default_factory=list)
    salary_min: int | None
    salary_max: int | None
    salary_currency: str | None
    posted_date: date | None
    application_deadline: date | None
    extracted_at: datetime | None
    status: JobStatus
    duplicate_of_job_id: int | None
    created_at: datetime
    updated_at: datetime


class JobCreateResponse(BaseModel):
    job: JobRead
    created: bool
    fetch_notice: dict | None = None


class JobListResponse(BaseModel):
    items: list[JobRead]
    total: int
    limit: int
    offset: int
