"""Turns a user-provided URL and/or description into a stored Job row.

No AI calls happen here -- this stage works with zero OpenAI API key
configured, per the requirement that basic job storage/parsing must not
depend on it.
"""

import hashlib
import logging
import re
from dataclasses import dataclass
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.enums import JobStatus
from app.models.job import Job
from app.services.job_parser import clean_html_to_text, clean_pasted_description, fetch_job_url, normalize_url

logger = logging.getLogger("app.job_ingestion")

MANUAL_INPUT_REQUIRED = {
    "status": "manual_input_required",
    "message": "Unable to extract job description automatically. Please paste the job description.",
}


class JobIngestionError(ValueError):
    pass


@dataclass
class IngestionResult:
    job: Job
    created: bool
    fetch_notice: dict | None = None


def _hash_description(text: str) -> str:
    return hashlib.sha256(text.strip().lower().encode("utf-8")).hexdigest()


def _normalize_identity_text(text: str | None) -> str:
    if not text:
        return ""
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def normalize_title(title: str | None) -> str:
    return _normalize_identity_text(title)


def normalize_company(company: str | None) -> str:
    return _normalize_identity_text(company)


def find_existing_job_by_url_or_text(db: Session, canonical_url: str | None, description_hash: str | None) -> Job | None:
    if canonical_url:
        existing = db.execute(select(Job).where(Job.canonical_url == canonical_url)).scalar_one_or_none()
        if existing:
            return existing
    if description_hash:
        existing = db.execute(select(Job).where(Job.description_hash == description_hash)).scalar_one_or_none()
        if existing:
            return existing
    return None


def find_possible_duplicate_by_identity(db: Session, job: Job) -> Job | None:
    """Post-analysis dedup pass: same normalized title + company + location
    as another job, once we actually know those fields. Flags the job
    rather than deleting/merging it -- detection without destructive
    side-effects."""

    if not (job.title and job.company):
        return None

    norm_title = normalize_title(job.title)
    norm_company = normalize_company(job.company)
    norm_location = (job.location or "").strip().lower()

    candidates = db.execute(
        select(Job).where(Job.id != job.id, Job.title.isnot(None), Job.company.isnot(None))
    ).scalars().all()

    for candidate in candidates:
        if (
            normalize_title(candidate.title) == norm_title
            and normalize_company(candidate.company) == norm_company
            and (candidate.location or "").strip().lower() == norm_location
        ):
            return candidate
    return None


def ingest_job(db: Session, url: str | None, description: str | None) -> IngestionResult:
    url = (url or "").strip() or None
    description = (description or "").strip() or None

    if not url and not description:
        raise JobIngestionError("Provide a url, a description, or both.")

    canonical_url = normalize_url(url) if url else None

    # If a description was given directly, clean it up front -- it's pure
    # text, no network involved -- so the dedup check below can compare
    # against the same hash that ends up stored.
    raw_content = description
    clean_description = clean_pasted_description(description) if description else None
    description_hash = _hash_description(clean_description) if clean_description else None

    existing = find_existing_job_by_url_or_text(db, canonical_url, description_hash)
    if existing:
        logger.info("job ingestion matched existing job id=%s", existing.id)
        return IngestionResult(job=existing, created=False)

    source = urlparse(canonical_url).netloc if canonical_url else "manual"
    fetch_notice = None

    if not clean_description and url:
        fetch_result = fetch_job_url(url)
        if not fetch_result.ok:
            logger.info("job url fetch unsuccessful, manual input required")
            fetch_notice = MANUAL_INPUT_REQUIRED
        else:
            raw_content = fetch_result.html
            clean_description = clean_html_to_text(fetch_result.html)
            description_hash = _hash_description(clean_description) if clean_description else None
            if not clean_description:
                fetch_notice = MANUAL_INPUT_REQUIRED

    job = Job(
        url=url,
        canonical_url=canonical_url,
        description_hash=description_hash,
        source=source,
        raw_content=raw_content,
        description=clean_description,
        status=JobStatus.DISCOVERED,
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    logger.info("job ingested id=%s has_description=%s", job.id, bool(job.description))

    return IngestionResult(job=job, created=True, fetch_notice=fetch_notice)
