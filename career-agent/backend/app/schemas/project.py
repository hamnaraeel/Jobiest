from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator


class ProjectResultBase(BaseModel):
    description: str = Field(..., min_length=1)
    metric: str | None = None
    verified: bool = False


class ProjectResultCreate(ProjectResultBase):
    pass


class ProjectResultRead(ProjectResultBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    evidence_ids: list[int] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class ProjectBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    problem: str | None = None
    solution: str | None = None
    technologies: list[str] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    github_url: HttpUrl | None = None
    demo_url: HttpUrl | None = None
    start_date: date | None = None
    end_date: date | None = None
    verified: bool = False

    @model_validator(mode="after")
    def _check_date_order(self):
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValueError("end_date cannot be before start_date")
        return self


class ProjectCreate(ProjectBase):
    profile_id: int
    results: list[ProjectResultCreate] = Field(default_factory=list)


class ProjectUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    problem: str | None = None
    solution: str | None = None
    technologies: list[str] | None = None
    skills: list[str] | None = None
    github_url: HttpUrl | None = None
    demo_url: HttpUrl | None = None
    start_date: date | None = None
    end_date: date | None = None
    verified: bool | None = None


class ProjectRead(ProjectBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    profile_id: int
    results: list[ProjectResultRead] = Field(default_factory=list)
    evidence_ids: list[int] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime
