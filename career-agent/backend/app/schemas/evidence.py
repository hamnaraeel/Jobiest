from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, HttpUrl

from app.models.enums import EntityType, SourceType


class EvidenceLinkBase(BaseModel):
    entity_type: EntityType
    entity_id: int


class EvidenceLinkCreate(EvidenceLinkBase):
    pass


class EvidenceLinkRead(EvidenceLinkBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    evidence_id: int


class EvidenceBase(BaseModel):
    source_type: SourceType
    source_name: str = Field(..., min_length=1, max_length=255)
    source_url: HttpUrl | None = None
    description: str | None = None
    verified: bool = False


class EvidenceCreate(EvidenceBase):
    profile_id: int
    links: list[EvidenceLinkCreate] = Field(default_factory=list)


class EvidenceUpdate(BaseModel):
    source_type: SourceType | None = None
    source_name: str | None = None
    source_url: HttpUrl | None = None
    description: str | None = None
    verified: bool | None = None


class EvidenceRead(EvidenceBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    profile_id: int
    links: list[EvidenceLinkRead] = Field(default_factory=list)
    created_at: datetime
