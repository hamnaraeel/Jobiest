"""Step 6: deterministic job-search analytics. Every number here comes
from a plain SQL aggregation or a Python calculation over already-stored
data -- no LLM is ever used for counting, averaging, or aggregating
(spec section 68). Every formula is documented inline and mirrored in
docs/job-search-tracking.md.

Safe-division convention: any rate whose denominator is zero returns
`None` (not 0) -- a 0% rate and "not enough data to compute a rate" are
different facts, and returning 0 for both would misrepresent an empty
funnel stage as a proven-bad outcome (spec section 31).
"""

import statistics
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.application import Application
from app.models.application_followup import ApplicationFollowUp
from app.models.application_status_history import ApplicationStatusHistory
from app.models.cover_letter import CoverLetter
from app.models.cv_version import CVVersion
from app.models.enums import ApplicationStatus, FollowUpStatus, InterviewStatus, JobStatus, OfferStatus, RequirementCategory
from app.models.interview import Interview
from app.models.job import Job
from app.models.job_match import JobMatch
from app.models.job_requirement import JobRequirement
from app.models.offer import Offer
from app.models.profile import CareerProfile
from app.services.job_matching_service import normalize_skill, skills_equivalent

# A job counts as "shortlisted" (for the funnel) once its status shows it
# moved past pure discovery/analysis/matching into active consideration.
SHORTLISTED_OR_LATER = {
    JobStatus.SHORTLISTED, JobStatus.PREPARING, JobStatus.READY_TO_APPLY, JobStatus.APPLIED,
    JobStatus.WITHDRAWN, JobStatus.CLOSED, JobStatus.REJECTED, JobStatus.ARCHIVED,
}

# A status transition into one of these counts as "the employer
# responded" -- SUBMITTED itself doesn't (that's the application, not a
# response to it); GHOSTED/WITHDRAWN/CLOSED/FAILED explicitly don't.
RESPONSE_STATUSES = {
    ApplicationStatus.UNDER_REVIEW, ApplicationStatus.RECRUITER_CONTACT, ApplicationStatus.INTERVIEW,
    ApplicationStatus.TECHNICAL_INTERVIEW, ApplicationStatus.FINAL_INTERVIEW, ApplicationStatus.OFFER,
    ApplicationStatus.ACCEPTED, ApplicationStatus.REJECTED,
}


def _safe_ratio(numerator: int, denominator: int) -> float | None:
    if not denominator:
        return None
    return round(numerator / denominator * 100, 1)


def _duration_stats(deltas_days: list[float]) -> dict:
    if not deltas_days:
        return {"average": None, "median": None, "minimum": None, "maximum": None, "count": 0}
    return {
        "average": round(statistics.mean(deltas_days), 1),
        "median": round(statistics.median(deltas_days), 1),
        "minimum": round(min(deltas_days), 1),
        "maximum": round(max(deltas_days), 1),
        "count": len(deltas_days),
    }


def _applications_with_relations(db: Session) -> list[Application]:
    return db.execute(select(Application)).scalars().unique().all()


def _has_response(application: Application) -> bool:
    return any(h.new_status in RESPONSE_STATUSES for h in application.status_history)


def _first_response_at(application: Application) -> datetime | None:
    matches = [h.created_at for h in application.status_history if h.new_status in RESPONSE_STATUSES]
    return min(matches) if matches else None


def _first_interview_at(application: Application) -> datetime | None:
    timestamps = [i.scheduled_at or i.created_at for i in application.interviews]
    return min(timestamps) if timestamps else None


def _first_offer_at(application: Application) -> datetime | None:
    timestamps = [o.created_at for o in application.offers]
    return min(timestamps) if timestamps else None


# --- Funnel / conversion / velocity ---------------------------------------


def funnel(db: Session) -> dict:
    """Discovered -> Shortlisted -> Applied -> Response -> Interview ->
    Offer -> Accepted (spec section 30)."""

    discovered = db.execute(select(func.count(Job.id))).scalar_one()
    shortlisted = db.execute(select(func.count(Job.id)).where(Job.status.in_(SHORTLISTED_OR_LATER))).scalar_one()

    applications = _applications_with_relations(db)
    applied_apps = [a for a in applications if a.submitted_at is not None]
    responded_apps = [a for a in applied_apps if _has_response(a)]
    interviewed_apps = [a for a in applied_apps if a.interviews]
    offered_apps = [a for a in applied_apps if a.offers]
    accepted = db.execute(select(func.count(Offer.id)).where(Offer.status == OfferStatus.ACCEPTED)).scalar_one()

    return {
        "discovered": discovered, "shortlisted": shortlisted, "applied": len(applied_apps),
        "responses": len(responded_apps), "interviews": len(interviewed_apps),
        "offers": len(offered_apps), "accepted": accepted,
    }


def conversion_rates(f: dict) -> dict:
    """All rates are percentages, safe-divided (spec section 31)."""

    return {
        "shortlist_rate": _safe_ratio(f["shortlisted"], f["discovered"]),
        "application_rate": _safe_ratio(f["applied"], f["shortlisted"]),
        "response_rate": _safe_ratio(f["responses"], f["applied"]),
        "interview_rate": _safe_ratio(f["interviews"], f["applied"]),
        "offer_rate": _safe_ratio(f["offers"], f["interviews"]),
        "overall_offer_rate": _safe_ratio(f["offers"], f["applied"]),
    }


def response_time_stats(db: Session) -> dict:
    applications = _applications_with_relations(db)
    deltas = []
    for a in applications:
        if a.submitted_at is None:
            continue
        first_response = _first_response_at(a)
        if first_response:
            deltas.append((first_response - a.submitted_at).total_seconds() / 86400)
    return _duration_stats(deltas)


def interview_time_stats(db: Session) -> dict:
    applications = _applications_with_relations(db)
    deltas = []
    for a in applications:
        if a.submitted_at is None:
            continue
        first_interview = _first_interview_at(a)
        if first_interview:
            deltas.append((first_interview - a.submitted_at).total_seconds() / 86400)
    return _duration_stats(deltas)


def offer_time_stats(db: Session) -> dict:
    applications = _applications_with_relations(db)
    deltas = []
    for a in applications:
        if a.submitted_at is None:
            continue
        first_offer = _first_offer_at(a)
        if first_offer:
            deltas.append((first_offer - a.submitted_at).total_seconds() / 86400)
    return _duration_stats(deltas)


def velocity(db: Session) -> dict:
    """Applications/jobs-reviewed/interviews/offers per week and per
    month, based on actual elapsed history (spec section 46)."""

    now = datetime.now(timezone.utc)
    first_job = db.execute(select(func.min(Job.created_at))).scalar_one()
    weeks = max((now - first_job).days / 7, 1) if first_job else 1

    total_applications = db.execute(select(func.count(Application.id)).where(Application.submitted_at.isnot(None))).scalar_one()
    total_jobs = db.execute(select(func.count(Job.id))).scalar_one()
    total_interviews = db.execute(select(func.count(Interview.id))).scalar_one()
    total_offers = db.execute(select(func.count(Offer.id))).scalar_one()

    return {
        "applications_per_week": round(total_applications / weeks, 2),
        "applications_per_month": round(total_applications / weeks * 4.345, 2),
        "jobs_reviewed_per_week": round(total_jobs / weeks, 2),
        "interviews_per_month": round(total_interviews / weeks * 4.345, 2),
        "offers_per_month": round(total_offers / weeks * 4.345, 2),
    }


def overview(db: Session) -> dict:
    f = funnel(db)
    return {
        "funnel": f,
        "conversion_rates": conversion_rates(f),
        "time_to_response_days": response_time_stats(db),
        "time_to_interview_days": interview_time_stats(db),
        "time_to_offer_days": offer_time_stats(db),
        "velocity": velocity(db),
    }


# --- Status breakdown --------------------------------------------------


def status_breakdown(db: Session) -> dict:
    rows = db.execute(select(Application.status, func.count(Application.id)).group_by(Application.status)).all()
    return {status.value: count for status, count in rows}


# --- Company / role analytics -------------------------------------------


def _group_applications_by(db: Session, key_fn) -> dict:
    applications = _applications_with_relations(db)
    groups: dict[str, list[Application]] = defaultdict(list)
    for a in applications:
        if a.submitted_at is None or a.job is None:
            continue
        key = key_fn(a)
        if key:
            groups[key].append(a)

    result = {}
    for key, apps in groups.items():
        interviews = sum(1 for a in apps if a.interviews)
        offers = sum(1 for a in apps if a.offers)
        responses = sum(1 for a in apps if _has_response(a))
        match_scores = [a.job.match.overall_score for a in apps if a.job.match]
        result[key] = {
            "applications": len(apps), "interviews": interviews, "offers": offers,
            "response_rate": _safe_ratio(responses, len(apps)),
            "average_match_score": round(statistics.mean(match_scores), 1) if match_scores else None,
        }
    return result


def company_analytics(db: Session) -> dict:
    return _group_applications_by(db, lambda a: a.job.company)


def role_analytics(db: Session) -> dict:
    """Grouped by job title -- the closest thing to a "role" this schema
    tracks (spec section 37)."""

    return _group_applications_by(db, lambda a: a.job.title)


def source_analytics(db: Session) -> dict:
    """Grouped by Application.source (spec section 41)."""

    return _group_applications_by(db, lambda a: a.source or "unknown")


# --- Skill demand / gap analysis ------------------------------------------


def skill_analytics(db: Session, top_n: int = 20) -> dict:
    """Which skills appear most often in jobs actually applied to (spec
    section 38), plus a potential-skill-gap comparison against the
    Career Profile (spec section 39) -- presented as an observation, not
    an instruction, and never used to modify the profile automatically."""

    applied_job_ids = db.execute(
        select(Application.job_id).where(Application.submitted_at.isnot(None)).distinct()
    ).scalars().all()
    if not applied_job_ids:
        return {"demand": {}, "potential_gaps": []}

    requirements = db.execute(
        select(JobRequirement).where(
            JobRequirement.job_id.in_(applied_job_ids),
            JobRequirement.category == RequirementCategory.TECHNICAL_SKILL,
            JobRequirement.skill_name.isnot(None),
        )
    ).scalars().all()

    demand = Counter(r.skill_name for r in requirements)

    profile = db.execute(select(CareerProfile).order_by(CareerProfile.id).limit(1)).scalar_one_or_none()
    profile_skill_names = [s.name for s in profile.skills] if profile else []

    gaps = []
    for skill_name, count in demand.most_common():
        has_it = any(skills_equivalent(skill_name, ps) for ps in profile_skill_names)
        if not has_it:
            gaps.append({"skill": skill_name, "jobs_requested": count})

    return {
        "demand": dict(demand.most_common(top_n)),
        "potential_gaps": gaps[:top_n],
    }


# --- Match score analysis -------------------------------------------------


MATCH_SCORE_BUCKETS = [(90, 100), (80, 89), (70, 79), (60, 69), (0, 59)]


def match_score_analysis(db: Session) -> dict:
    """Applications and interviews bucketed by match score (spec section
    40) -- purely descriptive ("observed application performance"), never
    framed as a causal claim."""

    applications = _applications_with_relations(db)
    result = {}
    for low, high in MATCH_SCORE_BUCKETS:
        label = f"{low}-{high}"
        bucket_apps = [
            a for a in applications
            if a.submitted_at is not None and a.job and a.job.match and low <= a.job.match.overall_score <= high
        ]
        result[label] = {
            "applications": len(bucket_apps),
            "interviews": sum(1 for a in bucket_apps if a.interviews),
            "offers": sum(1 for a in bucket_apps if a.offers),
        }
    return result


# --- CV / cover letter version analytics -----------------------------------


def cv_version_analytics(db: Session) -> dict:
    """Observed performance per CV version and per cover-letter version
    (spec sections 42-43). Deliberately worded as "observed application
    performance" everywhere this is surfaced -- never a causal claim."""

    applications = [a for a in _applications_with_relations(db) if a.submitted_at is not None]

    def _by(attr_id, version_lookup):
        groups: dict[int, list[Application]] = defaultdict(list)
        for a in applications:
            vid = getattr(a, attr_id)
            if vid:
                groups[vid].append(a)
        result = {}
        for vid, apps in groups.items():
            version = version_lookup(vid)
            # version_name alone isn't a safe grouping key: two different
            # CVVersion/CoverLetter rows can legitimately share the same
            # name (e.g. two applications to similarly-titled roles at the
            # same company -- cv_customization_service names versions
            # "{job.title} - {job.company} - V{n}", which collides across
            # jobs sharing both). Suffixing the real row id keeps every
            # version's stats separate while staying human-readable.
            label = f"{version.version_name} [#{vid}]" if version else f"#{vid}"
            result[label] = {
                "applications": len(apps),
                "interviews": sum(1 for a in apps if a.interviews),
                "offers": sum(1 for a in apps if a.offers),
            }
        return result

    cv_lookup = {cv.id: cv for cv in db.execute(select(CVVersion)).scalars().all()}
    cl_lookup = {cl.id: cl for cl in db.execute(select(CoverLetter)).scalars().all()}

    return {
        "cv_versions": _by("cv_version_id", lambda vid: cv_lookup.get(vid)),
        "cover_letter_versions": _by("cover_letter_id", lambda vid: cl_lookup.get(vid)),
    }


# --- Weekly / monthly -----------------------------------------------------


def _period_bounds(reference: date, period: str) -> tuple[datetime, datetime]:
    if period == "week":
        start = reference - timedelta(days=reference.weekday())
        end = start + timedelta(days=7)
    else:
        start = reference.replace(day=1)
        next_month = (start.replace(day=28) + timedelta(days=4)).replace(day=1)
        end = next_month
    return (
        datetime.combine(start, datetime.min.time(), tzinfo=timezone.utc),
        datetime.combine(end, datetime.min.time(), tzinfo=timezone.utc),
    )


def _period_metrics(db: Session, start: datetime, end: datetime) -> dict:
    jobs_discovered = db.execute(select(func.count(Job.id)).where(Job.created_at >= start, Job.created_at < end)).scalar_one()
    jobs_shortlisted = db.execute(
        select(func.count(Job.id)).where(Job.status.in_(SHORTLISTED_OR_LATER), Job.updated_at >= start, Job.updated_at < end)
    ).scalar_one()
    applications = db.execute(
        select(func.count(Application.id)).where(Application.submitted_at >= start, Application.submitted_at < end)
    ).scalar_one()
    responses = db.execute(
        select(func.count(func.distinct(ApplicationStatusHistory.application_id))).where(
            ApplicationStatusHistory.new_status.in_(RESPONSE_STATUSES),
            ApplicationStatusHistory.created_at >= start, ApplicationStatusHistory.created_at < end,
        )
    ).scalar_one()
    interviews = db.execute(
        select(func.count(Interview.id)).where(Interview.created_at >= start, Interview.created_at < end)
    ).scalar_one()
    offers = db.execute(
        select(func.count(Offer.id)).where(Offer.created_at >= start, Offer.created_at < end)
    ).scalar_one()
    return {
        "jobs_discovered": jobs_discovered, "jobs_shortlisted": jobs_shortlisted, "applications": applications,
        "responses": responses, "interviews": interviews, "offers": offers,
    }


def weekly_analytics(db: Session, reference: date | None = None) -> dict:
    reference = reference or datetime.now(timezone.utc).date()
    start, end = _period_bounds(reference, "week")
    metrics = _period_metrics(db, start, end)
    return {"period": "week", "start": start.date().isoformat(), "end": (end.date() - timedelta(days=1)).isoformat(), **metrics}


def monthly_analytics(db: Session, reference: date | None = None) -> dict:
    reference = reference or datetime.now(timezone.utc).date()
    start, end = _period_bounds(reference, "month")
    metrics = _period_metrics(db, start, end)
    return {"period": "month", "start": start.date().isoformat(), "end": (end.date() - timedelta(days=1)).isoformat(), **metrics}


# --- Dashboard -------------------------------------------------------------


def dashboard(db: Session) -> dict:
    """GET /dashboard (spec sections 28-29)."""

    jobs_total = db.execute(select(func.count(Job.id))).scalar_one()
    jobs_discovered = db.execute(select(func.count(Job.id)).where(Job.status == JobStatus.DISCOVERED)).scalar_one()
    jobs_shortlisted = db.execute(select(func.count(Job.id)).where(Job.status.in_(SHORTLISTED_OR_LATER))).scalar_one()

    applications = _applications_with_relations(db)
    submitted = [a for a in applications if a.submitted_at is not None]
    prepared = [a for a in applications if a.status not in (ApplicationStatus.ABANDONED, ApplicationStatus.FAILED)]
    under_review = [a for a in submitted if a.status == ApplicationStatus.UNDER_REVIEW]

    interviews_total = db.execute(select(func.count(Interview.id))).scalar_one()
    interviews_scheduled = db.execute(select(func.count(Interview.id)).where(Interview.status == InterviewStatus.SCHEDULED)).scalar_one()
    offers_total = db.execute(select(func.count(Offer.id))).scalar_one()
    rejections = sum(1 for a in submitted if a.status == ApplicationStatus.REJECTED)
    withdrawals = sum(1 for a in submitted if a.status == ApplicationStatus.WITHDRAWN)

    followups_pending = db.execute(select(func.count(ApplicationFollowUp.id)).where(ApplicationFollowUp.status == FollowUpStatus.PENDING)).scalar_one()
    followups_due_today = db.execute(
        select(func.count(ApplicationFollowUp.id)).where(
            ApplicationFollowUp.status == FollowUpStatus.PENDING,
            ApplicationFollowUp.due_date <= datetime.now(timezone.utc).date(),
        )
    ).scalar_one()

    return {
        "jobs": {"total": jobs_total, "discovered": jobs_discovered, "shortlisted": jobs_shortlisted},
        "applications": {"total": len(applications), "prepared": len(prepared), "submitted": len(submitted), "under_review": len(under_review)},
        "interviews": {"total": interviews_total, "scheduled": interviews_scheduled},
        "offers": {"total": offers_total},
        "followups": {"pending": followups_pending, "due_today": followups_due_today},
        "analytics": overview(db) | {"rejections": rejections, "withdrawals": withdrawals},
    }
