"""Arbeitnow adapter (Step 8).

Arbeitnow publishes a free public JSON API
(https://www.arbeitnow.com/api/job-board-api), no key required. There's
no server-side keyword search, so filtering happens client-side against
title + tags, same as RemoteOK/WWR. `remote` is a real boolean on each
listing, so workplace_type is set directly from it rather than guessed.
"""

import html
import logging
from datetime import datetime, timezone

import requests

from app.discovery.base import DiscoveredJob, DiscoveryQuery
from app.discovery.matching import matches_keywords
from app.models.enums import WorkplaceType
from app.services.job_parser import USER_AGENT, clean_html_to_text

logger = logging.getLogger("app.discovery.arbeitnow")

REQUEST_TIMEOUT_SECONDS = 10
SOURCE_NAME = "arbeitnow"


def search_arbeitnow(query: DiscoveryQuery) -> list[DiscoveredJob]:
    try:
        response = requests.get(
            "https://www.arbeitnow.com/api/job-board-api",
            headers={"User-Agent": USER_AGENT},
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
    except requests.RequestException:
        logger.warning("arbeitnow request failed")
        return []

    if response.status_code != 200:
        logger.warning("arbeitnow unexpected status=%s", response.status_code)
        return []

    try:
        payload = response.json()
    except ValueError:
        logger.warning("arbeitnow non-JSON response")
        return []

    results: list[DiscoveredJob] = []
    for item in payload.get("data", []):
        title = (item.get("title") or "").strip()
        slug = item.get("slug")
        if not title or not slug:
            continue

        searchable = " ".join([title, *(item.get("tags") or [])])
        if not matches_keywords(searchable, query.keywords):
            continue

        # Arbeitnow's description comes back double HTML-escaped (e.g.
        # literal "&lt;div&gt;" text, not a real <div> tag) -- unescape
        # once before stripping tags, or the tags survive as visible text.
        raw_description = html.unescape(item.get("description") or "")
        created_at = item.get("created_at")
        posted_date = None
        if created_at:
            try:
                posted_date = datetime.fromtimestamp(created_at, tz=timezone.utc).date().isoformat()
            except (ValueError, OSError, OverflowError):
                posted_date = None

        results.append(DiscoveredJob(
            source=SOURCE_NAME,
            external_job_id=slug,
            title=title,
            company=item.get("company_name") or "Unknown",
            url=item.get("url") or "",
            description=clean_html_to_text(raw_description) if raw_description else None,
            location=item.get("location") or None,
            workplace_type=WorkplaceType.REMOTE if item.get("remote") else None,
            posted_date=posted_date,
        ))
        if len(results) >= query.limit_per_source:
            break

    return results
