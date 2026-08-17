"""Adzuna adapter (Step 8).

Adzuna is a job-search aggregator with a free, official, keyed public API
(https://api.adzuna.com/v1/api/jobs/{country}/search/{page}) -- register
a free app_id/app_key at https://developer.adzuna.com/. Real keyword +
location search, unlike the Greenhouse/Lever per-company adapters.
"""

import logging

import requests

from app.discovery.base import DiscoveredJob, DiscoveryQuery, DiscoverySourceError
from app.models.enums import JobEmploymentType
from app.services.job_parser import USER_AGENT

logger = logging.getLogger("app.discovery.adzuna")

REQUEST_TIMEOUT_SECONDS = 10
SOURCE_NAME = "adzuna"
_CURRENCY_BY_COUNTRY = {"us": "USD", "gb": "GBP", "ca": "CAD", "au": "AUD", "de": "EUR", "fr": "EUR"}


def _employment_type(contract_time: str | None) -> JobEmploymentType:
    if contract_time == "full_time":
        return JobEmploymentType.FULL_TIME
    if contract_time == "part_time":
        return JobEmploymentType.PART_TIME
    return JobEmploymentType.UNKNOWN


def search_adzuna(query: DiscoveryQuery, app_id: str, app_key: str, country: str = "us") -> list[DiscoveredJob]:
    if not app_id or not app_key:
        raise DiscoverySourceError("Adzuna is not configured -- set ADZUNA_APP_ID and ADZUNA_APP_KEY.")

    locations = query.locations or [None]
    results: list[DiscoveredJob] = []
    seen_ids: set[str] = set()

    for location in locations:
        if len(results) >= query.limit_per_source:
            break

        params = {
            "app_id": app_id,
            "app_key": app_key,
            "results_per_page": min(query.limit_per_source, 50),
            "content-type": "application/json",
        }
        if query.keywords:
            params["what_or"] = " ".join(query.keywords)
        if location:
            params["where"] = location

        try:
            response = requests.get(
                f"https://api.adzuna.com/v1/api/jobs/{country}/search/1",
                params=params,
                headers={"User-Agent": USER_AGENT},
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
        except requests.RequestException as exc:
            raise DiscoverySourceError(f"Adzuna request failed: {exc}") from exc

        if response.status_code != 200:
            raise DiscoverySourceError(f"Adzuna returned HTTP {response.status_code}: {response.text[:200]}")

        try:
            payload = response.json()
        except ValueError as exc:
            raise DiscoverySourceError("Adzuna returned a non-JSON response") from exc

        for job in payload.get("results", []):
            job_id = str(job.get("id") or "")
            if not job_id or job_id in seen_ids:
                continue
            seen_ids.add(job_id)

            results.append(DiscoveredJob(
                source=SOURCE_NAME,
                external_job_id=job_id,
                title=(job.get("title") or "").strip(),
                company=(job.get("company") or {}).get("display_name") or "Unknown",
                url=job.get("redirect_url") or "",
                description=job.get("description"),
                location=(job.get("location") or {}).get("display_name"),
                employment_type=_employment_type(job.get("contract_time")),
                salary_min=int(job["salary_min"]) if job.get("salary_min") else None,
                salary_max=int(job["salary_max"]) if job.get("salary_max") else None,
                salary_currency=_CURRENCY_BY_COUNTRY.get(country),
                posted_date=(job.get("created") or "")[:10] or None,
            ))
            if len(results) >= query.limit_per_source:
                break

    return results
