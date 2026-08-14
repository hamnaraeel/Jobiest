from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.enums import RequirementCategory, RequirementImportance


class JobRequirementRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    job_id: int
    requirement_text: str
    category: RequirementCategory
    importance: RequirementImportance
    required: bool
    skill_name: str | None
    years_required: float | None
    education_requirement: str | None
    evidence_required: bool
    created_at: datetime
