from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.discovery.base import ALL_SOURCES
from app.models.enums import DiscoveryTrigger


class DiscoveryRunRequest(BaseModel):
    sources: list[str] | None = Field(
        None, description=f"Subset of sources to search this run. Omit to use all configured sources. Valid: {ALL_SOURCES}"
    )
    keywords: list[str] | None = Field(None, description="Override the profile/goal-derived keywords for this run only.")
    locations: list[str] | None = Field(None, description="Override the profile/goal-derived locations for this run only.")
    companies: list[str] | None = Field(None, description="Override the goal-derived target companies (Greenhouse/Lever) for this run only.")


class DiscoveryRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    trigger: DiscoveryTrigger
    sources: list[str]
    query: dict
    results: dict
    jobs_found: int
    jobs_created: int
    started_at: datetime
    finished_at: datetime | None
    created_at: datetime


class DiscoveryRunListResponse(BaseModel):
    items: list[DiscoveryRunRead]
    total: int


class DiscoverySourceStatus(BaseModel):
    source: str
    configured: bool
    requires_api_key: bool
    note: str
