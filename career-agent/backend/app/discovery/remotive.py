"""Remotive adapter (Step 8).

Remotive publishes a free public JSON API
(https://remotive.com/api/remote-jobs), no key required, with real
server-side keyword search via `?search=`. Per Remotive's own API terms
(returned in the payload's own warning/notice fields), results must
attribute back to Remotive -- see the "source" field stored on every
discovered Job -- and the API should not be polled more than a few times
a day, which this app's default once-a-day discovery schedule already
respects. All Remotive listings are remote by definition.
"""

import logging

import requests

from app.discovery.base import DiscoveredJob, DiscoveryQuery
from app.models.enums import JobEmploymentType, WorkplaceType
from app.services.job_parser import USER_AGENT, clean_html_to_text

logger = logging.getLogger("app.discovery.remotive")

REQUEST_TIMEOUT_SECONDS = 10
SOURCE_NAME = "remotive"

_EMPLOYMENT_TYPE_MAP = {
    "full_time": JobEmploymentType.FULL_TIME,
    "part_time": JobEmploymentType.PART_TIME,
    "contract": JobEmploymentType.CONTRACT,
    "freelance": JobEmploymentType.CONTRACT,
    "internship": JobEmploymentType.INTERNSHIP,
}


def search_remotive(query: DiscoveryQuery) -> list[DiscoveredJob]:
    params = {"limit": query.limit_per_source}
    if query.keywords:
        # Remotive's `search` param matches title/company/tags server-side
        # -- only one term is accepted, so the first (usually the most
        # specific) keyword is used and results aren't re-filtered
        # client-side, matching how Adzuna's single `what_or` is used.
        params["search"] = query.keywords[0]

    try:
        response = requests.get(
            "https://remotive.com/api/remote-jobs",
            params=params,
            headers={"User-Agent": USER_AGENT},
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
    except requests.RequestException:
        logger.warning("remotive request failed")
        return []

    if response.status_code != 200:
        logger.warning("remotive unexpected status=%s", response.status_code)
        return []

    try:
        payload = response.json()
    except ValueError:
        logger.warning("remotive non-JSON response")
        return []

    results: list[DiscoveredJob] = []
    for item in payload.get("jobs", []):
        job_id = item.get("id")
        title = (item.get("title") or "").strip()
        if not job_id or not title:
            continue

        raw_description = item.get("description") or ""
        results.append(DiscoveredJob(
            source=SOURCE_NAME,
            external_job_id=str(job_id),
            title=title,
            company=item.get("company_name") or "Unknown",
            url=item.get("url") or "",
            description=clean_html_to_text(raw_description) if raw_description else None,
            location=item.get("candidate_required_location"),
            employment_type=_EMPLOYMENT_TYPE_MAP.get(item.get("job_type") or "", JobEmploymentType.UNKNOWN),
            workplace_type=WorkplaceType.REMOTE,
            posted_date=(item.get("publication_date") or "")[:10] or None,
        ))
        if len(results) >= query.limit_per_source:
            break

    return results
