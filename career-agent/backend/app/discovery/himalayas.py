"""Himalayas adapter (Step 8).

Himalayas publishes a free public JSON API
(https://himalayas.app/jobs/api/search), no key/auth required, with real
server-side keyword + location search via `q=`/`country=`. Per Himalayas'
own API terms, results must link back to the original Himalayas URL and
credit Himalayas as the source -- both satisfied by storing `url` as the
real applicationLink and `source` as "himalayas" on every discovered Job,
same attribution pattern as Remotive. All Himalayas listings are remote
by definition.
"""

import logging
from datetime import datetime, timezone

import requests

from app.discovery.base import DiscoveredJob, DiscoveryQuery
from app.models.enums import JobEmploymentType, WorkplaceType
from app.services.job_parser import USER_AGENT, clean_html_to_text

logger = logging.getLogger("app.discovery.himalayas")

REQUEST_TIMEOUT_SECONDS = 10
SOURCE_NAME = "himalayas"

_EMPLOYMENT_TYPE_MAP = {
    "full time": JobEmploymentType.FULL_TIME,
    "part time": JobEmploymentType.PART_TIME,
    "contractor": JobEmploymentType.CONTRACT,
    "temporary": JobEmploymentType.TEMPORARY,
    "intern": JobEmploymentType.INTERNSHIP,
}


def search_himalayas(query: DiscoveryQuery) -> list[DiscoveredJob]:
    params = {"limit": min(query.limit_per_source, 20)}
    if query.keywords:
        params["q"] = query.keywords[0]
    if query.locations:
        params["country"] = query.locations[0]

    try:
        response = requests.get(
            "https://himalayas.app/jobs/api/search",
            params=params,
            headers={"User-Agent": USER_AGENT},
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
    except requests.RequestException:
        logger.warning("himalayas request failed")
        return []

    if response.status_code != 200:
        logger.warning("himalayas unexpected status=%s", response.status_code)
        return []

    try:
        payload = response.json()
    except ValueError:
        logger.warning("himalayas non-JSON response")
        return []

    results: list[DiscoveredJob] = []
    for item in payload.get("jobs", []):
        title = (item.get("title") or "").strip()
        guid = item.get("guid")
        if not title or not guid:
            continue

        raw_description = item.get("description") or ""
        pub_date = item.get("pubDate")
        posted_date = None
        if pub_date:
            try:
                posted_date = datetime.fromtimestamp(pub_date, tz=timezone.utc).date().isoformat()
            except (ValueError, OSError, OverflowError):
                posted_date = None

        results.append(DiscoveredJob(
            source=SOURCE_NAME,
            external_job_id=guid,
            title=title,
            company=item.get("companyName") or "Unknown",
            url=item.get("applicationLink") or guid,
            description=clean_html_to_text(raw_description) if raw_description else None,
            location=", ".join(item.get("locationRestrictions") or []) or None,
            employment_type=_EMPLOYMENT_TYPE_MAP.get((item.get("employmentType") or "").lower(), JobEmploymentType.UNKNOWN),
            workplace_type=WorkplaceType.REMOTE,
            salary_min=item.get("minSalary"),
            salary_max=item.get("maxSalary"),
            salary_currency=item.get("currency"),
            posted_date=posted_date,
        ))
        if len(results) >= query.limit_per_source:
            break

    return results
