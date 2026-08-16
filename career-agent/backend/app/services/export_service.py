"""Application export -- CSV and JSON (spec section 63). Reads existing
data only; never computes or invents anything."""

import csv
import io
import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.application import Application

EXPORT_COLUMNS = [
    "id", "company", "role", "job_url", "application_url", "status", "priority",
    "match_score", "submitted_date", "cv_version", "cover_letter_version",
    "interview_status", "offer_status", "notes",
]


def _row_for(application: Application) -> dict:
    job = application.job
    latest_interview = max(application.interviews, key=lambda i: i.created_at, default=None)
    latest_offer = max(application.offers, key=lambda o: o.created_at, default=None)
    notes = "; ".join(n.content for n in application.notes)
    return {
        "id": application.id,
        "company": job.company if job else None,
        "role": job.title if job else None,
        "job_url": job.url if job else None,
        "application_url": application.application_url,
        "status": application.status.value,
        "priority": application.priority.value,
        "match_score": job.match.overall_score if job and job.match else None,
        "submitted_date": application.submitted_at.date().isoformat() if application.submitted_at else None,
        "cv_version": application.cv_version.version_name if application.cv_version else None,
        "cover_letter_version": application.cover_letter.version_name if application.cover_letter else None,
        "interview_status": latest_interview.status.value if latest_interview else None,
        "offer_status": latest_offer.status.value if latest_offer else None,
        "notes": notes,
    }


def export_applications(db: Session, include_archived: bool = False) -> list[dict]:
    stmt = select(Application)
    if not include_archived:
        stmt = stmt.where(Application.archived.is_(False))
    applications = db.execute(stmt.order_by(Application.id)).scalars().all()
    return [_row_for(a) for a in applications]


def to_csv(rows: list[dict]) -> str:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=EXPORT_COLUMNS)
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    return buffer.getvalue()


def to_json(rows: list[dict]) -> str:
    return json.dumps(rows, indent=2, default=str)
