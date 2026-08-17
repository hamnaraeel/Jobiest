"""RemoteOK adapter (Step 8).

RemoteOK publishes its full remote-jobs feed at a single public JSON
endpoint (https://remoteok.com/api), no key required. Per RemoteOK's own
API terms (returned as the feed's first element), we attribute results
back to RemoteOK -- see the "source" field stored on every discovered
Job. There's no server-side keyword search, so filtering by the profile's
target roles happens client-side against title + tags.
"""

import logging

import requests

from app.discovery.base import DiscoveredJob, DiscoveryQuery
from app.discovery.matching import matches_keywords
from app.services.job_parser import USER_AGENT, clean_html_to_text

logger = logging.getLogger("app.discovery.remoteok")

REQUEST_TIMEOUT_SECONDS = 10
SOURCE_NAME = "remoteok"


def search_remoteok(query: DiscoveryQuery) -> list[DiscoveredJob]:
    try:
        response = requests.get(
            "https://remoteok.com/api",
            headers={"User-Agent": USER_AGENT},
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
    except requests.RequestException:
        logger.warning("remoteok request failed")
        return []

    if response.status_code != 200:
        logger.warning("remoteok unexpected status=%s", response.status_code)
        return []

    try:
        items = response.json()
    except ValueError:
        logger.warning("remoteok non-JSON response")
        return []

    results: list[DiscoveredJob] = []
    for item in items:
        # The feed's first element is a legal/attribution notice, not a
        # job -- it has no "id" field, which we use to skip it.
        if not item.get("id"):
            continue

        position = (item.get("position") or "").strip()
        searchable = " ".join([position, *(item.get("tags") or [])])
        if not position or not matches_keywords(searchable, query.keywords):
            continue

        raw_description = item.get("description") or ""
        results.append(DiscoveredJob(
            source=SOURCE_NAME,
            external_job_id=str(item["id"]),
            title=position,
            company=item.get("company") or "Unknown",
            url=item.get("url") or item.get("apply_url") or "",
            description=clean_html_to_text(raw_description) if raw_description else None,
            location=item.get("location") or None,
            salary_min=item.get("salary_min") or None,
            salary_max=item.get("salary_max") or None,
            posted_date=(item.get("date") or "")[:10] or None,
        ))
        if len(results) >= query.limit_per_source:
            break

    return results
