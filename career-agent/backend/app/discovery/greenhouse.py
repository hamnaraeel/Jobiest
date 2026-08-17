"""Greenhouse job-board API adapter (Step 8).

Greenhouse has no cross-company search -- each company's public postings
live at a per-company "board token" endpoint
(https://boards-api.greenhouse.io/v1/boards/{token}/jobs). There is no
key or authentication required; this is Greenhouse's own public job-board
API, the same one embedded in every company's careers page widget. We
therefore search by iterating the companies from the user's job-search
goal / career profile (see discovery_service.py), not by free-text
keyword -- a 404 for a given token just means that company isn't on
Greenhouse, which is expected and silently skipped, not an error.
"""

import html
import logging

import requests

from app.discovery.base import DiscoveredJob, DiscoveryQuery
from app.discovery.matching import company_to_board_token, matches_keywords
from app.services.job_parser import USER_AGENT, clean_html_to_text

logger = logging.getLogger("app.discovery.greenhouse")

REQUEST_TIMEOUT_SECONDS = 10
SOURCE_NAME = "greenhouse"


def search_greenhouse(query: DiscoveryQuery) -> list[DiscoveredJob]:
    results: list[DiscoveredJob] = []

    for company in query.companies:
        if len(results) >= query.limit_per_source:
            break
        token = company_to_board_token(company)
        if not token:
            continue

        try:
            response = requests.get(
                f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs",
                params={"content": "true"},
                headers={"User-Agent": USER_AGENT},
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
        except requests.RequestException:
            logger.warning("greenhouse request failed for company=%s", company)
            continue

        if response.status_code == 404:
            continue  # this company isn't on Greenhouse -- not an error
        if response.status_code != 200:
            logger.warning("greenhouse unexpected status=%s company=%s", response.status_code, company)
            continue

        try:
            jobs = response.json().get("jobs", [])
        except ValueError:
            logger.warning("greenhouse non-JSON response for company=%s", company)
            continue

        for job in jobs:
            title = (job.get("title") or "").strip()
            if not title or not matches_keywords(title, query.keywords):
                continue

            raw_content = job.get("content") or ""
            description = clean_html_to_text(html.unescape(raw_content)) if raw_content else None

            results.append(DiscoveredJob(
                source=SOURCE_NAME,
                external_job_id=str(job.get("id")),
                title=title,
                company=job.get("company_name") or company,
                url=job.get("absolute_url") or "",
                description=description,
                location=(job.get("location") or {}).get("name"),
                posted_date=(job.get("first_published") or job.get("updated_at") or "")[:10] or None,
            ))
            if len(results) >= query.limit_per_source:
                break

    return results
