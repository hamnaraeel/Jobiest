from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, HttpUrl

from app.models.enums import RemotePreference


class CareerProfileBase(BaseModel):
    full_name: str = Field(..., min_length=1, max_length=255)
    professional_title: str = Field(..., min_length=1, max_length=255)
    email: EmailStr
    phone: str | None = None
    city: str | None = None
    country: str | None = None
    linkedin_url: HttpUrl | None = None
    github_url: HttpUrl | None = None
    portfolio_url: HttpUrl | None = None

    current_summary: str | None = None
    target_roles: list[str] = Field(default_factory=list)
    preferred_industries: list[str] = Field(default_factory=list)
    preferred_locations: list[str] = Field(default_factory=list)
    remote_preference: RemotePreference | None = None
    years_of_experience: float | None = Field(default=None, ge=0, le=80)


class CareerProfileCreate(CareerProfileBase):
    pass


class CareerProfileUpdate(BaseModel):
    full_name: str | None = None
    professional_title: str | None = None
    email: EmailStr | None = None
    phone: str | None = None
    city: str | None = None
    country: str | None = None
    linkedin_url: HttpUrl | None = None
    github_url: HttpUrl | None = None
    portfolio_url: HttpUrl | None = None
    current_summary: str | None = None
    target_roles: list[str] | None = None
    preferred_industries: list[str] | None = None
    preferred_locations: list[str] | None = None
    remote_preference: RemotePreference | None = None
    years_of_experience: float | None = Field(default=None, ge=0, le=80)


class CareerProfileRead(CareerProfileBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: datetime


class CareerProfileExport(BaseModel):
    """Full export shape returned by GET /profile/export and consumed by
    POST /profile/import. Nested collections are added lazily by the
    service layer to avoid a hard import cycle with the other schema
    modules."""

    model_config = ConfigDict(from_attributes=True)

    profile: CareerProfileRead
    educations: list[dict] = Field(default_factory=list)
    experiences: list[dict] = Field(default_factory=list)
    projects: list[dict] = Field(default_factory=list)
    skills: list[dict] = Field(default_factory=list)
    certifications: list[dict] = Field(default_factory=list)
    achievements: list[dict] = Field(default_factory=list)
    research_items: list[dict] = Field(default_factory=list)
    evidence: list[dict] = Field(default_factory=list)
