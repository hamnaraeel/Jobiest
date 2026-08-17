"""Shared types for Step 8's job discovery adapters.

Each adapter module (greenhouse.py, lever.py, remoteok.py,
weworkremotely.py, adzuna.py, usajobs.py) talks to one public, ToS-
compliant job source and returns a list of DiscoveredJob -- plain,
already-structured data (title/company/location/etc known up front,
unlike Step 2's manual paste/URL flow which needs AI extraction to learn
those). Deliberately excludes LinkedIn and Indeed: both explicitly
prohibit automated scraping in their ToS and run active anti-bot
enforcement (LinkedIn has litigated and won against scrapers -- hiQ v.
LinkedIn). Those stay a manual paste/URL flow through Step 2, same as
before this step existed.
"""

from dataclasses import dataclass, field

from app.models.enums import JobEmploymentType, WorkplaceType

ALL_SOURCES = ["greenhouse", "lever", "remoteok", "weworkremotely", "adzuna", "usajobs"]
COMPANY_SOURCES = {"greenhouse", "lever"}


class DiscoverySourceError(Exception):
    """Raised by an adapter when the source could not be queried at all
    (network failure, unexpected response shape, auth failure). Discovery
    orchestration catches this per-source so one source failing doesn't
    stop the others from running."""


@dataclass
class DiscoveredJob:
    source: str
    external_job_id: str
    title: str
    company: str
    url: str
    description: str | None = None
    location: str | None = None
    employment_type: JobEmploymentType | None = None
    workplace_type: WorkplaceType | None = None
    salary_min: int | None = None
    salary_max: int | None = None
    salary_currency: str | None = None
    posted_date: str | None = None  # ISO date string (YYYY-MM-DD), if known


@dataclass
class DiscoveryQuery:
    """What to search for -- built from the career profile / job-search
    goal by discovery_service, never guessed by an adapter itself."""

    keywords: list[str] = field(default_factory=list)
    locations: list[str] = field(default_factory=list)
    companies: list[str] = field(default_factory=list)
    remote_only: bool = False
    limit_per_source: int = 25
