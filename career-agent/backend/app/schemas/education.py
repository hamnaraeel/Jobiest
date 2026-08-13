from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator


class EducationBase(BaseModel):
    institution: str = Field(..., min_length=1, max_length=255)
    degree: str = Field(..., min_length=1, max_length=255)
    field: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    location: str | None = None
    grade: str | None = None
    relevant_coursework: list[str] = Field(default_factory=list)
    thesis: str | None = None
    description: str | None = None
    verified: bool = False

    @model_validator(mode="after")
    def _check_date_order(self):
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValueError("end_date cannot be before start_date")
        return self


class EducationCreate(EducationBase):
    profile_id: int


class EducationUpdate(BaseModel):
    institution: str | None = None
    degree: str | None = None
    field: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    location: str | None = None
    grade: str | None = None
    relevant_coursework: list[str] | None = None
    thesis: str | None = None
    description: str | None = None
    verified: bool | None = None


class EducationRead(EducationBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    profile_id: int
    evidence_ids: list[int] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime
