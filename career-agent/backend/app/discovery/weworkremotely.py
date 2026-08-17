"""We Work Remotely adapter (Step 8).

WWR publishes a public combined RSS feed across every category
(https://weworkremotely.com/remote-jobs.rss), no key required. Item
titles are formatted "Company: Job Title" -- split on the first colon.
No server-side keyword search, so filtering happens client-side.
"""

import logging
import xml.etree.ElementTree as ET
from datetime import datetime

import requests

from app.discovery.base import DiscoveredJob, DiscoveryQuery
from app.discovery.matching import matches_keywords
from app.services.job_parser import USER_AGENT, clean_html_to_text

logger = logging.getLogger("app.discovery.weworkremotely")

REQUEST_TIMEOUT_SECONDS = 10
SOURCE_NAME = "weworkremotely"
FEED_URL = "https://weworkremotely.com/remote-jobs.rss"


def _parse_pub_date(text: str | None) -> str | None:
    if not text:
        return None
    try:
        return datetime.strptime(text, "%a, %d %b %Y %H:%M:%S %z").date().isoformat()
    except ValueError:
        return None


def search_weworkremotely(query: DiscoveryQuery) -> list[DiscoveredJob]:
    try:
        response = requests.get(FEED_URL, headers={"User-Agent": USER_AGENT}, timeout=REQUEST_TIMEOUT_SECONDS)
    except requests.RequestException:
        logger.warning("weworkremotely request failed")
        return []

    if response.status_code != 200:
        logger.warning("weworkremotely unexpected status=%s", response.status_code)
        return []

    try:
        root = ET.fromstring(response.content)
    except ET.ParseError:
        logger.warning("weworkremotely feed did not parse as XML")
        return []

    results: list[DiscoveredJob] = []
    for item in root.findall(".//item"):
        raw_title = (item.findtext("title") or "").strip()
        if not raw_title:
            continue
        company, _, position = raw_title.partition(": ")
        if not position:
            company, position = "Unknown", raw_title

        if not matches_keywords(f"{position} {item.findtext('category') or ''}", query.keywords):
            continue

        link = item.findtext("link") or item.findtext("guid") or ""
        raw_description = item.findtext("description") or ""

        results.append(DiscoveredJob(
            source=SOURCE_NAME,
            external_job_id=link or raw_title,
            title=position.strip(),
            company=company.strip(),
            url=link,
            description=clean_html_to_text(raw_description) if raw_description else None,
            location=item.findtext("region"),
            posted_date=_parse_pub_date(item.findtext("pubDate")),
        ))
        if len(results) >= query.limit_per_source:
            break

    return results
