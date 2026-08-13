from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator


class CertificationBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    issuer: str = Field(..., min_length=1, max_length=255)
    issue_date: date | None = None
    expiry_date: date | None = None
    credential_id: str | None = None
    credential_url: HttpUrl | None = None
    verified: bool = False

    @model_validator(mode="after")
    def _check_date_order(self):
        if self.issue_date and self.expiry_date and self.expiry_date < self.issue_date:
            raise ValueError("expiry_date cannot be before issue_date")
        return self


class CertificationCreate(CertificationBase):
    profile_id: int


class CertificationUpdate(BaseModel):
    name: str | None = None
    issuer: str | None = None
    issue_date: date | None = None
    expiry_date: date | None = None
    credential_id: str | None = None
    credential_url: HttpUrl | None = None
    verified: bool | None = None


class CertificationRead(CertificationBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    profile_id: int
    evidence_ids: list[int] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime
