from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.enums import ResumeImportStatus


class ResumeImportRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    profile_id: int | None
    filename: str
    parsed_data: dict
    warnings: list[str]
    status: ResumeImportStatus
    confirmed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ResumeImportListResponse(BaseModel):
    items: list[ResumeImportRead]
    total: int


class ResumeImportConfirmRequest(BaseModel):
    profile_id: int | None = None
