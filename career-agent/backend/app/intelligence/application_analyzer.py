"""Per-job and per-application intelligence assembly (spec sections 32,
47). Combines job_prioritizer, cv_analyzer, skill_gap_analyzer, and
Step 6's tracking_service/followup_service -- this module doesn't
compute anything new itself, it assembles what the other analyzers
already produce into the "application strategy" / "application
intelligence" shape the API needs.
"""

from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.intelligence import cv_analyzer, job_prioritizer
from app.intelligence.confidence import confidence_from_completeness
from app.models.application import Application
from app.models.enums import ApplicationMaterialStatus
from app.models.job import Job
from app.services import followup_service, tracking_service


def company_response_rates(db: Session) -> dict[str, float]:
    from app.services.analytics_service import company_analytics

    result = {}
    for company, stats in company_analytics(db).items():
        if stats.get("response_rate") is not None:
            result[company] = stats["response_rate"] / 100
    return result


def source_response_rates(db: Session) -> dict[str, float]:
    from app.services.analytics_service import source_analytics

    result = {}
    for source, stats in source_analytics(db).items():
        if stats.get("response_rate") is not None:
            result[source] = stats["response_rate"] / 100
    return result


@dataclass
class JobStrategy:
    priority: job_prioritizer.PriorityBreakdown
    opportunity: job_prioritizer.OpportunityBreakdown
    strong_areas: list[str] = field(default_factory=list)
    potential_concerns: list[str] = field(default_factory=list)
    cv_focus: str | None = None
    cover_letter_focus: str | None = None


def build_job_strategy(db: Session, job: Job, profile) -> JobStrategy:
    """GET /intelligence/jobs/{job_id} (spec sections 32, 46)."""

    match = job.match
    priority = job_prioritizer.compute_priority(
        job, match, profile, company_response_rates=company_response_rates(db), source_response_rates=source_response_rates(db),
    )
    opportunity = job_prioritizer.compute_opportunity_score(
        job, match, company_response_rates=company_response_rates(db), source_response_rates=source_response_rates(db),
    )

    strong_areas = [m.get("requirement") for m in (match.matched_requirements if match else [])][:5]
    potential_concerns = [m.get("requirement") for m in (match.missing_requirements if match else [])][:5]

    cv_focus = None
    cover_letter_focus = None
    if strong_areas:
        cv_focus = f"Highlight experience with {strong_areas[0]}."
    if potential_concerns:
        cover_letter_focus = f"Address the gap in {potential_concerns[0]} by connecting related experience to the role's requirements."

    return JobStrategy(
        priority=priority, opportunity=opportunity, strong_areas=strong_areas,
        potential_concerns=potential_concerns, cv_focus=cv_focus, cover_letter_focus=cover_letter_focus,
    )


@dataclass
class ApplicationQuality:
    ready: bool
    match_complete: bool
    cv_approved: bool
    cover_letter_approved: bool
    questions_complete: bool
    checks: dict = field(default_factory=dict)
    score: float = 0.0  # fraction of checks passed


def assess_application_quality(application: Application) -> ApplicationQuality:
    """Transparent components only (spec section 47) -- never a fake
    single "AI quality score.\""""

    match_complete = bool(application.job and application.job.match)
    cv_approved = bool(application.cv_version and application.cv_version.status == ApplicationMaterialStatus.APPROVED)
    cover_letter_approved = application.cover_letter is None or application.cover_letter.status == ApplicationMaterialStatus.APPROVED
    fields_ok = not any(f.required and f.status.value not in ("filled", "skipped") for f in application.fields)

    checks = {
        "match_computed": match_complete, "cv_approved": cv_approved,
        "cover_letter_approved": cover_letter_approved, "required_fields_complete": fields_ok,
    }
    passed = sum(1 for v in checks.values() if v)
    return ApplicationQuality(
        ready=all(checks.values()), match_complete=match_complete, cv_approved=cv_approved,
        cover_letter_approved=cover_letter_approved, questions_complete=fields_ok,
        checks=checks, score=round(passed / len(checks), 2),
    )


def build_application_intelligence(db: Session, application: Application) -> dict:
    """GET /intelligence/applications/{application_id} (spec section 47)."""

    from app.services.profile_service import get_default_profile

    profile = get_default_profile(db)
    quality = assess_application_quality(application)

    cv_gap = None
    if application.cv_version:
        cv_gap = cv_analyzer.analyze_job_cv_gap(application.job, application.cv_version, application.job.match, profile)

    interview_context = tracking_service.build_interview_context(db, application)
    suggested_followup = followup_service.suggested_followup_date(application)

    historical_context = {}
    if application.job and application.job.company:
        from app.services.analytics_service import company_analytics

        historical_context = company_analytics(db).get(application.job.company, {})

    return {
        "quality": quality,
        "match_score": application.job.match.overall_score if application.job and application.job.match else None,
        "cv_gap": cv_gap,
        "cover_letter_word_count": application.cover_letter.word_count if application.cover_letter else None,
        "missing_requirements": cv_gap.missing if cv_gap else [],
        "interview_context": interview_context,
        "suggested_followup_date": suggested_followup,
        "historical_context_for_company": historical_context,
    }
