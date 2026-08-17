"""Lever job-board API adapter (Step 8).

Same shape as Greenhouse: no cross-company search, one public per-company
endpoint (https://api.lever.co/v0/postings/{token}), no key required.
Iterates the companies from the user's job-search goal / career profile;
a 404 means that company isn't on Lever and is silently skipped.
"""

import logging
from datetime import datetime, timezone

import requests

from app.discovery.base import DiscoveredJob, DiscoveryQuery
from app.discovery.matching import company_to_board_token, matches_keywords
from app.models.enums import JobEmploymentType, WorkplaceType
from app.services.job_parser import USER_AGENT

logger = logging.getLogger("app.discovery.lever")

REQUEST_TIMEOUT_SECONDS = 10
SOURCE_NAME = "lever"

_WORKPLACE_MAP = {"remote": WorkplaceType.REMOTE, "onsite": WorkplaceType.ONSITE, "hybrid": WorkplaceType.HYBRID}


def _employment_type(commitment: str | None) -> JobEmploymentType:
    text = (commitment or "").lower()
    if "intern" in text:
        return JobEmploymentType.INTERNSHIP
    if "contract" in text:
        return JobEmploymentType.CONTRACT
    if "part" in text:
        return JobEmploymentType.PART_TIME
    if "full" in text:
        return JobEmploymentType.FULL_TIME
    return JobEmploymentType.UNKNOWN


def search_lever(query: DiscoveryQuery) -> list[DiscoveredJob]:
    results: list[DiscoveredJob] = []

    for company in query.companies:
        if len(results) >= query.limit_per_source:
            break
        token = company_to_board_token(company)
        if not token:
            continue

        try:
            response = requests.get(
                f"https://api.lever.co/v0/postings/{token}",
                params={"mode": "json"},
                headers={"User-Agent": USER_AGENT},
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
        except requests.RequestException:
            logger.warning("lever request failed for company=%s", company)
            continue

        if response.status_code == 404:
            continue
        if response.status_code != 200:
            logger.warning("lever unexpected status=%s company=%s", response.status_code, company)
            continue

        try:
            postings = response.json()
        except ValueError:
            logger.warning("lever non-JSON response for company=%s", company)
            continue
        if not isinstance(postings, list):
            continue

        for job in postings:
            title = (job.get("text") or "").strip()
            if not title or not matches_keywords(title, query.keywords):
                continue

            categories = job.get("categories") or {}
            salary = job.get("salaryRange") or {}
            created_at_ms = job.get("createdAt")
            posted_date = None
            if isinstance(created_at_ms, (int, float)):
                posted_date = datetime.fromtimestamp(created_at_ms / 1000, tz=timezone.utc).date().isoformat()

            results.append(DiscoveredJob(
                source=SOURCE_NAME,
                external_job_id=str(job.get("id")),
                title=title,
                company=company,
                url=job.get("hostedUrl") or "",
                description=job.get("descriptionPlain") or job.get("descriptionBodyPlain"),
                location=categories.get("location"),
                employment_type=_employment_type(categories.get("commitment")),
                workplace_type=_WORKPLACE_MAP.get(job.get("workplaceType")),
                salary_min=salary.get("min"),
                salary_max=salary.get("max"),
                salary_currency=salary.get("currency"),
                posted_date=posted_date,
            ))
            if len(results) >= query.limit_per_source:
                break

    return results
