"""Company/source/role strategy, career direction, personalized
strategy, and the weekly review (spec sections 22-26, 33-34). Builds
entirely on Step 6's already-computed analytics (`analytics_service`) --
this module's job is picking out the best-performing groups and phrasing
them as cautious, evidence-backed observations, never causal claims and
never a command ("you should abandon X").
"""

from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.intelligence.confidence import SMALL_SAMPLE_THRESHOLD, confidence_from_sample_size
from app.intelligence.skill_gap_analyzer import analyze_skill_gaps, missing_skill_gaps
from app.services import analytics_service
from app.services.profile_service import get_default_profile


@dataclass
class BestPerformer:
    label: str | None
    stats: dict | None
    observation: str
    confidence: float
    confidence_reason: str


def _best_by_response_rate(groups: dict[str, dict], noun: str) -> BestPerformer:
    eligible = {label: stats for label, stats in groups.items() if stats.get("applications", 0) > 0}
    if not eligible:
        return BestPerformer(None, None, f"No {noun} data yet.", 0.0, "No historical data available yet.")

    best_label = max(eligible, key=lambda label: (eligible[label].get("response_rate") or 0, eligible[label]["applications"]))
    best_stats = eligible[best_label]
    total_sample = sum(s["applications"] for s in eligible.values())
    confidence, confidence_reason = confidence_from_sample_size(best_stats["applications"])

    rate = best_stats.get("response_rate")
    rate_text = f"{rate}% response rate" if rate is not None else "no recorded responses yet"
    if best_stats["applications"] < SMALL_SAMPLE_THRESHOLD:
        observation = (
            f"Early signal: {best_label} has performed best among {noun} so far ({rate_text} on "
            f"{best_stats['applications']} application(s)), but there isn't enough historical data yet to be confident."
        )
    else:
        observation = f"Your historical response rate has been highest for {best_label} ({rate_text}, {noun}, observed over {best_stats['applications']} applications)."

    return BestPerformer(best_label, best_stats, observation, confidence, confidence_reason)


def company_strategy(db: Session) -> BestPerformer:
    return _best_by_response_rate(analytics_service.company_analytics(db), "companies")


def source_strategy(db: Session) -> BestPerformer:
    return _best_by_response_rate(analytics_service.source_analytics(db), "sources")


def role_strategy(db: Session) -> BestPerformer:
    return _best_by_response_rate(analytics_service.role_analytics(db), "roles")


@dataclass
class CareerDirection:
    potential_direction: str | None
    evidence: dict
    observation: str


def career_direction(db: Session) -> CareerDirection:
    """Never "you should become X" -- always "potentially strong
    direction," backed by concrete evidence (spec section 26)."""

    role_perf = analytics_service.role_analytics(db)
    best_role = _best_by_response_rate(role_perf, "roles")
    profile = get_default_profile(db)
    gaps = analyze_skill_gaps(db, profile) if profile else []
    top_demand_skills = [g.skill for g in gaps[:5] if g.has_skill]

    if best_role.label is None:
        return CareerDirection(None, {}, "Not enough application history yet to suggest a career direction.")

    evidence = {
        "role": best_role.label, "stats": best_role.stats,
        "strong_skill_overlap": top_demand_skills,
    }
    observation = (
        f"Potentially strong direction: {best_role.label}. Evidence -- "
        f"{best_role.stats.get('applications', 0)} applications, "
        f"{best_role.stats.get('interviews', 0)} interviews, and skill overlap with frequently "
        f"demanded skills ({', '.join(top_demand_skills) or 'none identified'})."
    )
    return CareerDirection(best_role.label, evidence, observation)


@dataclass
class PersonalizedStrategy:
    strengths: list[str]
    weaknesses: list[str]
    best_role: BestPerformer
    best_source: BestPerformer
    top_skill_gaps: list[str]
    recommended_target_roles: list[str]
    application_strategy: str
    suggested_weekly_targets: dict


def personalized_strategy(db: Session) -> PersonalizedStrategy:
    """GET /intelligence/strategy (spec section 33)."""

    profile = get_default_profile(db)
    gaps = analyze_skill_gaps(db, profile) if profile else []
    missing = missing_skill_gaps(gaps)
    strong_skills = [g.skill for g in gaps if g.has_skill][:5]

    best_role = role_strategy(db)
    best_source = source_strategy(db)

    strengths = [f"Strong skill match: {s}" for s in strong_skills]
    if best_role.stats:
        strengths.append(best_role.observation)
    weaknesses = [f"Potential skill gap: {g.skill} ({round(g.demand_ratio * 100)}% of analyzed jobs)" for g in missing[:5]]

    overview = analytics_service.overview(db)
    funnel = overview["funnel"]
    suggested_weekly_targets = {
        "applications_per_week": max(3, round(funnel["applied"] / 4)) if funnel["applied"] else 5,
    }

    application_strategy = (
        f"Prioritize {best_role.label or 'roles matching your profile'} "
        f"via {best_source.label or 'your highest-performing source'} where possible."
    )

    return PersonalizedStrategy(
        strengths=strengths, weaknesses=weaknesses, best_role=best_role, best_source=best_source,
        top_skill_gaps=[g.skill for g in missing[:5]],
        recommended_target_roles=[best_role.label] if best_role.label else [],
        application_strategy=application_strategy, suggested_weekly_targets=suggested_weekly_targets,
    )


def weekly_review(db: Session) -> dict:
    """GET /intelligence/weekly-review (spec section 34)."""

    weekly = analytics_service.weekly_analytics(db)
    best_role = role_strategy(db)
    best_source = source_strategy(db)
    cv_perf = analytics_service.cv_version_analytics(db)["cv_versions"]

    strongest_cv = None
    if cv_perf:
        strongest_cv = max(cv_perf, key=lambda label: (cv_perf[label]["interviews"], cv_perf[label]["applications"]))

    profile = get_default_profile(db)
    gaps = analyze_skill_gaps(db, profile) if profile else []
    top_gap = next((g for g in gaps if not g.has_skill), None)

    match_buckets = analytics_service.match_score_analysis(db)
    high_bucket = match_buckets.get("90-100", {})
    low_bucket = match_buckets.get("60-69", {})
    observed_improvement = None
    if high_bucket.get("applications") and low_bucket.get("applications"):
        high_rate = high_bucket["interviews"] / high_bucket["applications"]
        low_rate = low_bucket["interviews"] / low_bucket["applications"]
        if high_rate > low_rate:
            observed_improvement = "Applications with a higher match score have shown a higher observed interview rate."

    recommendation = f"Focus next week on {best_role.label or 'your strongest-performing roles'}"
    if top_gap:
        recommendation += f"; consider {top_gap.skill} as a skill gap to address."

    return {
        "period": weekly,
        "best_performing_role": best_role.label,
        "best_performing_source": best_source.label,
        "strongest_cv": strongest_cv,
        "top_skill_gap": top_gap.skill if top_gap else None,
        "observed_improvement": observed_improvement,
        "recommendation": recommendation,
    }
