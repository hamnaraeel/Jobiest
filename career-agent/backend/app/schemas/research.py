from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ResearchBase(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    methodology: str | None = None
    datasets: list[str] = Field(default_factory=list)
    models: list[str] = Field(default_factory=list)
    results: list[str] = Field(default_factory=list)
    publications: list[str] = Field(default_factory=list)
    research_area: str | None = None
    technologies: list[str] = Field(default_factory=list)
    verified: bool = False


class ResearchCreate(ResearchBase):
    profile_id: int


class ResearchUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    methodology: str | None = None
    datasets: list[str] | None = None
    models: list[str] | None = None
    results: list[str] | None = None
    publications: list[str] | None = None
    research_area: str | None = None
    technologies: list[str] | None = None
    verified: bool | None = None


class ResearchRead(ResearchBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    profile_id: int
    evidence_ids: list[int] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime
