from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import ProficiencyLevel, SkillCategory


class SkillBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    category: SkillCategory
    proficiency: ProficiencyLevel | None = None
    years_used: float | None = Field(default=None, ge=0, le=60)
    verified: bool = False


class SkillCreate(SkillBase):
    profile_id: int


class SkillUpdate(BaseModel):
    name: str | None = None
    category: SkillCategory | None = None
    proficiency: ProficiencyLevel | None = None
    years_used: float | None = Field(default=None, ge=0, le=60)
    verified: bool | None = None


class SkillRead(SkillBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    profile_id: int
    evidence_ids: list[int] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime
