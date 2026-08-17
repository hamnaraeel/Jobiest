"""USAJobs adapter (Step 8).

USAJobs is the official U.S. federal government job board, with a free,
official, keyed public API (https://data.usajobs.gov/api/search) --
register at https://developer.usajobs.gov/ for an API key. Only relevant
if the user is open to federal roles; most target-role searches will
simply return zero results, which is not an error.
"""

import logging

import requests

from app.discovery.base import DiscoveredJob, DiscoveryQuery, DiscoverySourceError
from app.models.enums import JobEmploymentType

logger = logging.getLogger("app.discovery.usajobs")

REQUEST_TIMEOUT_SECONDS = 10
SOURCE_NAME = "usajobs"


def _employment_type(schedules: list[dict]) -> JobEmploymentType:
    names = " ".join((s.get("Name") or "") for s in schedules).lower()
    if "part" in names:
        return JobEmploymentType.PART_TIME
    if "full" in names:
        return JobEmploymentType.FULL_TIME
    return JobEmploymentType.UNKNOWN


def _to_int(value) -> int | None:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def search_usajobs(query: DiscoveryQuery, api_key: str, user_agent_email: str) -> list[DiscoveredJob]:
    if not api_key or not user_agent_email:
        raise DiscoverySourceError("USAJobs is not configured -- set USAJOBS_API_KEY and USAJOBS_USER_AGENT_EMAIL.")

    params = {"ResultsPerPage": min(query.limit_per_source, 500)}
    if query.keywords:
        params["Keyword"] = " ".join(query.keywords)
    if query.locations:
        params["LocationName"] = query.locations[0]

    try:
        response = requests.get(
            "https://data.usajobs.gov/api/search",
            params=params,
            headers={"User-Agent": user_agent_email, "Authorization-Key": api_key, "Host": "data.usajobs.gov"},
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
    except requests.RequestException as exc:
        raise DiscoverySourceError(f"USAJobs request failed: {exc}") from exc

    if response.status_code != 200:
        raise DiscoverySourceError(f"USAJobs returned HTTP {response.status_code}: {response.text[:200]}")

    try:
        payload = response.json()
    except ValueError as exc:
        raise DiscoverySourceError("USAJobs returned a non-JSON response") from exc

    items = (payload.get("SearchResult") or {}).get("SearchResultItems", [])
    results: list[DiscoveredJob] = []

    for item in items:
        descriptor = item.get("MatchedObjectDescriptor") or {}
        title = (descriptor.get("PositionTitle") or "").strip()
        if not title:
            continue

        remuneration = descriptor.get("PositionRemuneration") or [{}]
        pay = remuneration[0] if remuneration else {}
        summary = ((descriptor.get("UserArea") or {}).get("Details") or {}).get("JobSummary")

        results.append(DiscoveredJob(
            source=SOURCE_NAME,
            external_job_id=str(item.get("MatchedObjectId") or descriptor.get("PositionID") or ""),
            title=title,
            company=descriptor.get("OrganizationName") or descriptor.get("DepartmentName") or "U.S. Government",
            url=descriptor.get("PositionURI") or "",
            description=summary,
            location=descriptor.get("PositionLocationDisplay"),
            employment_type=_employment_type(descriptor.get("PositionSchedule") or []),
            salary_min=_to_int(pay.get("MinimumRange")),
            salary_max=_to_int(pay.get("MaximumRange")),
            salary_currency="USD",
            posted_date=(descriptor.get("PublicationStartDate") or "")[:10] or None,
        ))
        if len(results) >= query.limit_per_source:
            break

    return results
