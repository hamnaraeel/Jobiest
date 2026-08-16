from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import ApplicationMaterialStatus

ALLOWED_STYLES = ("professional", "concise", "research", "technical")
ALLOWED_LENGTHS = ("short", "medium", "long")


class EvidenceRef(BaseModel):
    source_type: str
    source_id: int


class CoverLetterGenerateRequest(BaseModel):
    style: str | None = Field(default=None, description=f"One of: {', '.join(ALLOWED_STYLES)}")
    length: str | None = Field(default=None, description=f"One of: {', '.join(ALLOWED_LENGTHS)}")
    focus: list[str] = Field(default_factory=list)
    instructions: str | None = None


class CoverLetterRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    job_id: int
    cv_version_id: int
    profile_id: int
    version_name: str
    version_number: int
    title: str
    content: str
    word_count: int
    status: ApplicationMaterialStatus
    source_evidence: list
    warnings: list[str]
    pdf_path: str | None
    created_at: datetime
    updated_at: datetime


class CoverLetterListResponse(BaseModel):
    items: list[CoverLetterRead]
    total: int


class CoverLetterStatusUpdateRequest(BaseModel):
    status: ApplicationMaterialStatus
