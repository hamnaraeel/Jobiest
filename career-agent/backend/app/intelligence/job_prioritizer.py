"""Deterministic job prioritization (spec sections 6-10). No LLM
involved -- a job's priority score is always a plain weighted sum of
concrete, explainable factors, each in [0, 1].

Weights are a module-level, overridable dict (same pattern as
job_matching_service.DEFAULT_WEIGHTS) rather than hard-coded inline, so
a caller can experiment with different weightings without editing the
scoring logic itself (spec section 7).
"""

import re
from dataclasses import dataclass, field
from datetime import date

from app.intelligence.confidence import confidence_from_completeness
from app.models.job import Job
from app.models.job_match import JobMatch
from app.models.profile import CareerProfile

DEFAULT_PRIORITY_WEIGHTS = {
    "match_score": 0.35,
    "required_skill_coverage": 0.20,
    "role_preference": 0.15,
    "experience_fit": 0.10,
    "location_fit": 0.05,
    "deadline": 0.05,
    "company_performance": 0.05,
    "source_performance": 0.05,
}


@dataclass
class PriorityBreakdown:
    score: int  # 0-100
    factors: dict[str, float]  # factor_name -> raw [0,1] value actually used
    reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    confidence: float = 0.0
    confidence_reason: str = ""


def _normalize_title(text: str | None) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", (text or "").lower()))


def _role_preference_score(job: Job, profile: CareerProfile | None) -> tuple[float | None, str | None]:
    if profile is None or not profile.target_roles:
        return None, None
    job_words = _normalize_title(job.title)
    if not job_words:
        return None, None
    for role in profile.target_roles:
        role_words = _normalize_title(role)
        if role_words and (role_words & job_words):
            return 1.0, f"Matches your target role '{role}'."
    return 0.2, "Title doesn't match any of your configured target roles."


def _location_fit_score(job: Job, profile: CareerProfile | None) -> tuple[float | None, str | None]:
    if profile is None:
        return None, None
    if profile.remote_preference and profile.remote_preference.value == "remote":
        if job.workplace_type and job.workplace_type.value == "remote":
            return 1.0, "Remote job matches your remote preference."
        if job.workplace_type:
            return 0.2, f"You prefer remote, this job is {job.workplace_type.value}."
        return None, None
    if profile.preferred_locations and job.location:
        job_location_words = _normalize_title(job.location)
        for loc in profile.preferred_locations:
            if _normalize_title(loc) & job_location_words:
                return 1.0, f"Location matches your preferred location '{loc}'."
        return 0.3, "Location doesn't match any of your preferred locations."
    return None, None


def _deadline_score(job: Job) -> tuple[float | None, str | None, str | None]:
    """Returns (score, reason, warning). Urgency, not desirability -- a
    very soon deadline scores high because it means "act now if you're
    going to act at all," not because it's inherently a better job."""

    if job.application_deadline is None:
        return None, None, "No application deadline is known for this job."
    days_left = (job.application_deadline - date.today()).days
    if days_left < 0:
        return 0.0, None, "The application deadline has already passed."
    if days_left <= 3:
        return 1.0, f"Deadline in {days_left} day(s) -- urgent.", None
    if days_left <= 7:
        return 0.8, f"Deadline in {days_left} days -- high urgency.", None
    if days_left <= 30:
        return 0.5, f"Deadline in {days_left} days.", None
    return 0.3, f"Deadline is {days_left} days away -- not urgent yet.", None


def _company_performance_score(job: Job, company_response_rates: dict[str, float]) -> tuple[float | None, str | None]:
    if not job.company:
        return None, None
    rate = company_response_rates.get(job.company)
    if rate is None:
        return None, None
    if rate >= 0.3:
        return 1.0, f"This company has an observed {round(rate * 100)}% response rate on your past applications."
    if rate > 0:
        return 0.5, f"This company has a modest observed {round(rate * 100)}% response rate on your past applications."
    return 0.1, "This company has not responded to your past applications."


def _source_performance_score(job: Job, source_response_rates: dict[str, float]) -> tuple[float | None, str | None]:
    if not job.source:
        return None, None
    rate = source_response_rates.get(job.source)
    if rate is None:
        return None, None
    if rate >= 0.3:
        return 1.0, f"Applications from '{job.source}' have an observed {round(rate * 100)}% response rate."
    if rate > 0:
        return 0.5, f"Applications from '{job.source}' have a modest observed {round(rate * 100)}% response rate."
    return 0.2, f"Applications from '{job.source}' have not historically gotten responses."


def compute_priority(
    job: Job, match: JobMatch | None, profile: CareerProfile | None,
    company_response_rates: dict[str, float] | None = None,
    source_response_rates: dict[str, float] | None = None,
    weights: dict[str, float] | None = None,
) -> PriorityBreakdown:
    weights = weights or DEFAULT_PRIORITY_WEIGHTS
    company_response_rates = company_response_rates or {}
    source_response_rates = source_response_rates or {}

    reasons: list[str] = []
    warnings: list[str] = []
    factors: dict[str, float] = {}

    if match is not None:
        factors["match_score"] = match.overall_score / 100
        reasons.append(f"Match score: {match.overall_score}%")
        skill_coverage = match.score_components.get("required_skills")
        if skill_coverage is not None:
            factors["required_skill_coverage"] = skill_coverage / 100
            reasons.append(f"Required skill coverage: {skill_coverage}%")
    else:
        warnings.append("This job has not been matched against your profile yet.")

    role_score, role_reason = _role_preference_score(job, profile)
    if role_score is not None:
        factors["role_preference"] = role_score
        reasons.append(role_reason)
    elif profile is None or not profile.target_roles:
        warnings.append("No target roles are configured, so role preference wasn't scored.")

    if match is not None:
        experience_component = match.score_components.get("experience")
        if experience_component is not None:
            factors["experience_fit"] = experience_component / 100
            reasons.append(f"Experience fit: {experience_component}%")

    location_score, location_reason = _location_fit_score(job, profile)
    if location_score is not None:
        factors["location_fit"] = location_score
        reasons.append(location_reason)
    else:
        warnings.append("Location/remote preference could not be scored (missing profile or job data).")

    deadline_score, deadline_reason, deadline_warning = _deadline_score(job)
    if deadline_score is not None:
        factors["deadline"] = deadline_score
        if deadline_reason:
            reasons.append(deadline_reason)
    if deadline_warning:
        warnings.append(deadline_warning)

    company_score, company_reason = _company_performance_score(job, company_response_rates)
    if company_score is not None:
        factors["company_performance"] = company_score
        reasons.append(company_reason)

    source_score, source_reason = _source_performance_score(job, source_response_rates)
    if source_score is not None:
        factors["source_performance"] = source_score
        reasons.append(source_reason)

    if not job.salary_min and not job.salary_max:
        warnings.append("Salary unknown.")

    used_weight_sum = sum(weights[key] for key in factors if key in weights)
    if used_weight_sum <= 0:
        score = 0
    else:
        weighted = sum(factors[key] * weights[key] for key in factors if key in weights)
        score = round(max(0.0, min(1.0, weighted / used_weight_sum)) * 100)

    confidence, confidence_reason = confidence_from_completeness(len(factors), len(weights))

    return PriorityBreakdown(
        score=score, factors=factors, reasons=reasons, warnings=warnings,
        confidence=confidence, confidence_reason=confidence_reason,
    )


DEFAULT_OPPORTUNITY_WEIGHTS = {
    "fit": 0.45,
    "company_performance": 0.20,
    "source_performance": 0.20,
    "profile_strength": 0.15,
}


@dataclass
class OpportunityBreakdown:
    score: int  # 0-100 -- "Application Opportunity Score", never a hiring probability
    factors: dict[str, float]
    reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def compute_opportunity_score(
    job: Job, match: JobMatch | None,
    company_response_rates: dict[str, float] | None = None,
    source_response_rates: dict[str, float] | None = None,
    weights: dict[str, float] | None = None,
) -> OpportunityBreakdown:
    """Deliberately NOT a "probability of getting hired" (spec section
    10) -- competition (how many other candidates, how the employer
    screens, etc.) isn't something this system can observe at all, so it
    is always reported as an explicit unknown rather than guessed into
    the score."""

    weights = weights or DEFAULT_OPPORTUNITY_WEIGHTS
    company_response_rates = company_response_rates or {}
    source_response_rates = source_response_rates or {}

    reasons: list[str] = []
    warnings: list[str] = ["Competitive pressure (how many other candidates, employer screening criteria) is unknown and not factored in."]
    factors: dict[str, float] = {}

    if match is not None:
        factors["fit"] = match.overall_score / 100
        reasons.append(f"Profile fit: {match.overall_score}%")
        skill_coverage = match.score_components.get("required_skills")
        if skill_coverage is not None:
            factors["profile_strength"] = skill_coverage / 100
            reasons.append(f"Required skill coverage: {skill_coverage}%")
    else:
        warnings.append("This job has not been matched against your profile yet.")

    company_score, company_reason = _company_performance_score(job, company_response_rates)
    if company_score is not None:
        factors["company_performance"] = company_score
        reasons.append(company_reason)

    source_score, source_reason = _source_performance_score(job, source_response_rates)
    if source_score is not None:
        factors["source_performance"] = source_score
        reasons.append(source_reason)

    used_weight_sum = sum(weights[key] for key in factors if key in weights)
    if used_weight_sum <= 0:
        score = 0
    else:
        weighted = sum(factors[key] * weights[key] for key in factors if key in weights)
        score = round(max(0.0, min(1.0, weighted / used_weight_sum)) * 100)

    return OpportunityBreakdown(score=score, factors=factors, reasons=reasons, warnings=warnings)
