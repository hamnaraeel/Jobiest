from datetime import date as date_type, datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import AchievementCategory


class AchievementBase(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    date: date_type | None = None
    category: AchievementCategory
    metric: str | None = None
    verified: bool = False


class AchievementCreate(AchievementBase):
    profile_id: int


class AchievementUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    date: date_type | None = None
    category: AchievementCategory | None = None
    metric: str | None = None
    verified: bool | None = None


class AchievementRead(AchievementBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    profile_id: int
    evidence_ids: list[int] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime
