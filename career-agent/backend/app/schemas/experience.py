from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.enums import EmploymentType


class ExperienceBulletBase(BaseModel):
    bullet: str = Field(..., min_length=1)
    skills: list[str] = Field(default_factory=list)
    verified: bool = False


class ExperienceBulletCreate(ExperienceBulletBase):
    pass


class ExperienceBulletRead(ExperienceBulletBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    experience_id: int
    evidence_ids: list[int] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class ExperienceBase(BaseModel):
    company: str = Field(..., min_length=1, max_length=255)
    role: str = Field(..., min_length=1, max_length=255)
    employment_type: EmploymentType | None = None
    location: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    currently_working: bool = False
    description: str | None = None
    technologies: list[str] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    achievements: list[str] = Field(default_factory=list)
    verified: bool = False

    @model_validator(mode="after")
    def _check_dates(self):
        if self.currently_working and self.end_date is not None:
            raise ValueError("end_date must be empty when currently_working is true")
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValueError("end_date cannot be before start_date")
        return self


class ExperienceCreate(ExperienceBase):
    profile_id: int
    bullets: list[ExperienceBulletCreate] = Field(default_factory=list)


class ExperienceUpdate(BaseModel):
    company: str | None = None
    role: str | None = None
    employment_type: EmploymentType | None = None
    location: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    currently_working: bool | None = None
    description: str | None = None
    technologies: list[str] | None = None
    skills: list[str] | None = None
    achievements: list[str] | None = None
    verified: bool | None = None


class ExperienceRead(ExperienceBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    profile_id: int
    bullets: list[ExperienceBulletRead] = Field(default_factory=list)
    evidence_ids: list[int] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime
