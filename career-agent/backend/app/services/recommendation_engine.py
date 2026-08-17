"""Orchestrates every app/intelligence/ analyzer into persisted
`Recommendation` rows (spec sections 4-9, 45). This is the only place
that writes Recommendation rows -- individual analyzers only compute and
return data, they never touch the database themselves.

Re-running generation doesn't pile up duplicates: a pending (NEW/VIEWED)
recommendation of the same type for the same job/application is updated
in place rather than duplicated. Anything the user has already acted on
(ACCEPTED/DISMISSED/COMPLETED) is left untouched -- that's their decision,
not something a later regeneration should silently overwrite.
"""

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.intelligence import career_insights, cv_analyzer, job_prioritizer, rejection_analyzer, skill_gap_analyzer
from app.intelligence.application_analyzer import company_response_rates, source_response_rates
from app.models.cv_version import CVVersion
from app.models.enums import (
    ApplicationStatus,
    JobStatus,
    PriorityLevel,
    RecommendationStatus,
    RecommendationType,
)
from app.models.job import Job
from app.models.recommendation import Recommendation
from app.services import followup_service
from app.services.profile_service import get_default_profile

logger = logging.getLogger("app.recommendation_engine")

# Jobs still under active consideration -- candidates for job_priority/job_skip.
_UNDECIDED_JOB_STATUSES = {JobStatus.DISCOVERED, JobStatus.ANALYZED, JobStatus.MATCHED, JobStatus.SHORTLISTED}

_PRIORITY_SCORE_LEVEL = [(85, PriorityLevel.CRITICAL), (65, PriorityLevel.HIGH), (40, PriorityLevel.MEDIUM)]


def _priority_level_for_score(score: int) -> PriorityLevel:
    for threshold, level in _PRIORITY_SCORE_LEVEL:
        if score >= threshold:
            return level
    return PriorityLevel.LOW


def _upsert(
    db: Session, type: RecommendationType, title: str, description: str, priority: PriorityLevel,
    confidence: float, confidence_reason: str, evidence: dict, action: str | None = None,
    related_job_id: int | None = None, related_application_id: int | None = None,
) -> Recommendation:
    existing = db.execute(
        select(Recommendation).where(
            Recommendation.type == type,
            Recommendation.related_job_id == related_job_id,
            Recommendation.related_application_id == related_application_id,
            Recommendation.status.in_([RecommendationStatus.NEW, RecommendationStatus.VIEWED]),
        )
    ).scalar_one_or_none()

    rec = existing or Recommendation(type=type, related_job_id=related_job_id, related_application_id=related_application_id)
    rec.title = title
    rec.description = description
    rec.priority = priority
    rec.confidence = confidence
    rec.confidence_reason = confidence_reason
    rec.evidence = evidence
    rec.action = action
    if not existing:
        db.add(rec)
    db.commit()
    db.refresh(rec)
    return rec


def generate_job_recommendations(db: Session, top_n: int = 10) -> list[Recommendation]:
    """JOB_PRIORITY for strong candidates, JOB_SKIP for weak ones (spec
    sections 6-9) -- never phrased as "don't apply," always as a
    low-priority signal the user can override."""

    profile = get_default_profile(db)
    jobs = db.execute(select(Job).where(Job.status.in_(_UNDECIDED_JOB_STATUSES))).scalars().all()
    company_rates = company_response_rates(db)
    source_rates = source_response_rates(db)

    scored = [(job, job_prioritizer.compute_priority(job, job.match, profile, company_rates, source_rates)) for job in jobs]
    scored.sort(key=lambda pair: pair[1].score, reverse=True)

    recommendations = []
    for job, breakdown in scored[:top_n]:
        if breakdown.score >= 65:
            rec = _upsert(
                db, RecommendationType.JOB_PRIORITY, f"Prioritize: {job.title or 'this job'} at {job.company or 'this company'}",
                f"Priority {breakdown.score}/100. " + " ".join(breakdown.reasons[:3]),
                _priority_level_for_score(breakdown.score), breakdown.confidence, breakdown.confidence_reason,
                {"score": breakdown.score, "factors": breakdown.factors, "reasons": breakdown.reasons, "warnings": breakdown.warnings},
                action="Review tailored CV and prepare application.", related_job_id=job.id,
            )
            recommendations.append(rec)
        elif breakdown.score < 40 and breakdown.factors:
            rec = _upsert(
                db, RecommendationType.JOB_SKIP, f"Low-priority application: {job.title or 'this job'} at {job.company or 'this company'}",
                f"Priority {breakdown.score}/100. " + " ".join(breakdown.reasons[:3] or ["Limited data available for this job."]),
                PriorityLevel.LOW, breakdown.confidence, breakdown.confidence_reason,
                {"score": breakdown.score, "factors": breakdown.factors, "reasons": breakdown.reasons, "warnings": breakdown.warnings},
                action="You may still choose to apply -- this is a low-priority signal, not a rejection.", related_job_id=job.id,
            )
            recommendations.append(rec)

    return recommendations


def generate_skill_gap_recommendations(db: Session, top_n: int = 5) -> list[Recommendation]:
    profile = get_default_profile(db)
    gaps = skill_gap_analyzer.missing_skill_gaps(skill_gap_analyzer.analyze_skill_gaps(db, profile))

    recommendations = []
    for gap in gaps[:top_n]:
        confidence = min(0.9, 0.3 + gap.demand_ratio)
        rec = _upsert(
            db, RecommendationType.SKILL_GAP, f"Potential skill gap: {gap.skill}",
            gap.suggested_next_step or gap.reason,
            PriorityLevel.HIGH if gap.priority == "high" else PriorityLevel.MEDIUM if gap.priority == "medium" else PriorityLevel.LOW,
            round(confidence, 2), f"Based on {gap.demand_count} analyzed jobs requesting this skill.",
            {"skill": gap.skill, "demand_count": gap.demand_count, "demand_ratio": gap.demand_ratio, "priority_score": gap.priority_score},
            action=gap.suggested_next_step,
        )
        recommendations.append(rec)
    return recommendations


def generate_cv_recommendations(db: Session) -> list[Recommendation]:
    """CV_IMPROVEMENT recommendations for the most recent CV version per
    job (spec sections 13, 54) -- only ever suggests including something
    already verified in the Career Profile, never a fabricated claim."""

    profile = get_default_profile(db)
    if profile is None:
        return []

    latest_per_job: dict[int, CVVersion] = {}
    for cv in db.execute(select(CVVersion).order_by(CVVersion.version_number)).scalars().all():
        latest_per_job[cv.job_id] = cv

    recommendations = []
    for cv in latest_per_job.values():
        report = cv_analyzer.analyze_profile_vs_cv(profile, cv)
        if not report.suggestions:
            continue
        rec = _upsert(
            db, RecommendationType.CV_IMPROVEMENT, f"CV improvement ideas for {cv.version_name}",
            " ".join(report.suggestions),
            PriorityLevel.MEDIUM, 0.7, "Based on a direct comparison with your verified Career Profile.",
            {
                "missing_skills": report.missing_skills, "missing_projects": report.missing_projects,
                "missing_achievements": report.missing_achievements, "duplicate_bullets": report.duplicate_bullets,
                "unsupported_claims": report.unsupported_claims,
            },
            action="Review and decide whether to regenerate this CV version with these additions.", related_job_id=cv.job_id,
        )
        recommendations.append(rec)
    return recommendations


def generate_rejection_pattern_recommendation(db: Session) -> Recommendation | None:
    analysis = rejection_analyzer.analyze_rejections(db)
    if not analysis.observations or analysis.total_rejected == 0:
        return None
    return _upsert(
        db, RecommendationType.REJECTION_PATTERN, "Rejection pattern observed",
        " ".join(analysis.observations),
        PriorityLevel.MEDIUM, analysis.confidence, analysis.confidence_reason,
        {
            "total_rejected": analysis.total_rejected, "reason_breakdown": analysis.reason_breakdown,
            "low_match_ratio": analysis.low_match_ratio,
        },
    )


def generate_source_strategy_recommendation(db: Session) -> Recommendation | None:
    best = career_insights.source_strategy(db)
    if best.label is None:
        return None
    return _upsert(
        db, RecommendationType.SOURCE_STRATEGY, f"Source strategy: {best.label}",
        best.observation, PriorityLevel.LOW, best.confidence, best.confidence_reason,
        best.stats or {},
    )


def generate_followup_recommendations(db: Session) -> list[Recommendation]:
    """FOLLOWUP recommendations for submitted applications past their
    suggested follow-up date with no follow-up recorded yet (spec
    sections 9, 11-12) -- always a suggestion, never auto-created."""

    from app.models.application import Application

    applications = db.execute(
        select(Application).where(Application.submitted_at.isnot(None), Application.status == ApplicationStatus.SUBMITTED)
    ).scalars().all()

    recommendations = []
    for application in applications:
        if application.followups:
            continue
        suggested = followup_service.suggested_followup_date(application)
        if suggested is None:
            continue
        rec = _upsert(
            db, RecommendationType.FOLLOWUP, f"Follow up on your application to {application.job.company if application.job else 'this company'}",
            f"No follow-up has been recorded yet. A follow-up around {suggested.isoformat()} is suggested "
            f"(settings.default_followup_days after submission).",
            PriorityLevel.MEDIUM, 0.6, "Based on the configured default follow-up window.",
            {"suggested_due_date": suggested.isoformat(), "submitted_at": application.submitted_at.isoformat()},
            action=f"Create a follow-up for {suggested.isoformat()} if you'd like a reminder.",
            related_application_id=application.id,
        )
        recommendations.append(rec)
    return recommendations


def generate_all(db: Session) -> list[Recommendation]:
    recommendations = []
    recommendations += generate_job_recommendations(db)
    recommendations += generate_skill_gap_recommendations(db)
    recommendations += generate_cv_recommendations(db)
    recommendations += generate_followup_recommendations(db)
    rejection_rec = generate_rejection_pattern_recommendation(db)
    if rejection_rec:
        recommendations.append(rejection_rec)
    source_rec = generate_source_strategy_recommendation(db)
    if source_rec:
        recommendations.append(source_rec)
    return recommendations
