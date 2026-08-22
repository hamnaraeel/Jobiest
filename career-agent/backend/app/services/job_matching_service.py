"""Deterministic job-match scoring engine.

Architecture (per the project spec): the LLM extracts requirements
(job_analysis_service) and may optionally phrase the final explanation
prose, but the score itself is always computed here, in plain Python,
from structured data. The LLM is never asked "do I match this job?" and
is never the final scoring authority.
"""

import logging
import re
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.client import AIConfigurationError, get_ai_client, get_ai_model
from app.ai.prompts import JOB_MATCH_EXPLANATION_PROMPT_V1
from app.ai.structured_outputs import MatchExplanationResult
from app.models.achievement import Achievement
from app.models.certification import Certification
from app.models.education import Education
from app.models.enums import JobStatus, MatchStatus, Recommendation, RequirementCategory, RequirementImportance
from app.models.experience import Experience
from app.models.job import Job
from app.models.job_match import JobMatch
from app.models.job_requirement import JobRequirement
from app.models.profile import CareerProfile
from app.models.project import Project
from app.models.research import Research
from app.services.profile_service import get_default_profile

logger = logging.getLogger("app.job_matching")

# Configurable: weights must sum to 1.0. Passed explicitly into
# compute_match() by callers/tests that want to tune them; these are just
# the defaults.
DEFAULT_WEIGHTS = {
    "required_skills": 0.30,
    "experience": 0.20,
    "technical_alignment": 0.15,
    "projects": 0.10,
    "education": 0.10,
    "research": 0.05,
    "preferred_skills": 0.05,
    "other_requirements": 0.05,
}

# Configurable: score >= apply -> "apply", score >= maybe -> "maybe", else "skip".
DEFAULT_RECOMMENDATION_THRESHOLDS = {"apply": 75, "maybe": 60}

# Pipeline order used by compute_match() to decide whether setting
# status=MATCHED would be an advance or a regression (see
# _set_matched_status below). Statuses not listed here (WITHDRAWN,
# CLOSED, REJECTED, ARCHIVED, SKIPPED) are treated as "never regress",
# since they're terminal/user-decided states outside the normal pipeline.
_JOB_STAGE_ORDER = [
    JobStatus.DISCOVERED, JobStatus.ANALYZED, JobStatus.MATCHED, JobStatus.SHORTLISTED,
    JobStatus.PREPARING, JobStatus.READY_TO_APPLY, JobStatus.APPLIED,
]

# Bumped whenever _score_components()/compute_match()'s scoring logic
# changes meaningfully -- stored on JobMatch.algorithm_version so Step 6's
# match-score analytics never silently mixes results from different
# scoring logic together (spec section 19).
MATCH_ALGORITHM_VERSION = "v1"

# Categories the schema (Step 1) simply has no field for. A missing
# security clearance is a fact; an untracked concept is not -- so these
# always come back "unknown", never "missing", per the never-assume rules.
UNASSESSABLE_CATEGORIES = {RequirementCategory.WORK_AUTHORIZATION, RequirementCategory.LANGUAGE}

_STATUS_SCORE = {
    MatchStatus.MATCHED: 1.0,
    MatchStatus.PARTIAL: 0.5,
    MatchStatus.UNKNOWN: 0.5,
    MatchStatus.MISSING: 0.0,
}


class MatchInputError(ValueError):
    pass


# --- Skill normalization -----------------------------------------------

_NORMALIZE_STRIP_WORDS = {"framework", "library", "language", "platform", "tool", "toolkit"}

SKILL_ALIAS_GROUPS: list[set[str]] = [
    {"pytorch", "torch"},
    {"tensorflow", "tf"},
    {"aws", "amazon web services"},
    {"gcp", "google cloud", "google cloud platform"},
    {"azure", "microsoft azure"},
    {"k8s", "kubernetes"},
    {"nlp", "natural language processing"},
    {"cv", "computer vision"},
    {"transformers", "hugging face transformers", "huggingface transformers", "hf transformers"},
    {"llm", "large language model", "large language models", "llms"},
    {"cnn", "convolutional neural network", "convolutional neural networks"},
    {"js", "javascript"},
    {"ts", "typescript"},
    {"postgres", "postgresql"},
]
_ALIAS_LOOKUP: dict[str, int] = {name: i for i, group in enumerate(SKILL_ALIAS_GROUPS) for name in group}


def normalize_skill(name: str) -> str:
    normalized = re.sub(r"[^a-z0-9\s]", " ", name.lower()).strip()
    words = [w for w in normalized.split() if w not in _NORMALIZE_STRIP_WORDS]
    return " ".join(words) if words else normalized


def skills_equivalent(a: str, b: str) -> bool:
    na, nb = normalize_skill(a), normalize_skill(b)
    if na == nb:
        return True
    group_a, group_b = _ALIAS_LOOKUP.get(na), _ALIAS_LOOKUP.get(nb)
    return group_a is not None and group_a == group_b


# --- Career data retrieval ----------------------------------------------
# Isolated behind this one function so a later step can replace it with
# vector_search() (embedding-based retrieval over the Step 1 embedding
# columns) without touching anything below it.


@dataclass
class SkillEvidence:
    verified: bool
    sources: list[str] = field(default_factory=list)


@dataclass
class ProfileContext:
    profile: CareerProfile
    skill_index: dict[str, SkillEvidence]
    experiences: list[Experience]
    projects: list[Project]
    research_items: list[Research]
    educations: list[Education]
    certifications: list[Certification]
    achievements: list[Achievement]


def get_relevant_career_data(db: Session, profile_id: int) -> ProfileContext:
    profile = db.get(CareerProfile, profile_id)
    if profile is None:
        raise MatchInputError(f"No career profile with id={profile_id}")

    skill_index: dict[str, SkillEvidence] = {}

    def register(name: str, verified: bool, source: str):
        key = normalize_skill(name)
        if not key:
            return
        entry = skill_index.setdefault(key, SkillEvidence(verified=False))
        entry.verified = entry.verified or verified
        if source not in entry.sources:
            entry.sources.append(source)

    for skill in profile.skills:
        register(skill.name, skill.verified, f"Skill: {skill.name}")

    for experience in profile.experiences:
        for tech in list(experience.technologies) + list(experience.skills):
            register(tech, experience.verified, f"Experience: {experience.role} at {experience.company}")
        for bullet in experience.bullets:
            for tech in bullet.skills:
                register(tech, bullet.verified, f"Experience: {experience.role} at {experience.company}")

    for project in profile.projects:
        for tech in list(project.technologies) + list(project.skills):
            register(tech, project.verified, f"Project: {project.name}")

    for research in profile.research_items:
        for tech in research.technologies:
            register(tech, research.verified, f"Research: {research.title}")

    return ProfileContext(
        profile=profile,
        skill_index=skill_index,
        experiences=list(profile.experiences),
        projects=list(profile.projects),
        research_items=list(profile.research_items),
        educations=list(profile.educations),
        certifications=list(profile.certifications),
        achievements=list(profile.achievements),
    )


def lookup_skill(ctx: ProfileContext, name: str) -> SkillEvidence | None:
    key = normalize_skill(name)
    if key in ctx.skill_index:
        return ctx.skill_index[key]
    group = _ALIAS_LOOKUP.get(key)
    if group is None:
        return None
    for other_key, evidence in ctx.skill_index.items():
        if _ALIAS_LOOKUP.get(other_key) == group:
            return evidence
    return None


# --- Requirement evaluation -----------------------------------------------


@dataclass
class RequirementEvaluation:
    requirement: JobRequirement
    status: MatchStatus
    evidence: list[str] = field(default_factory=list)
    reason: str | None = None

    def to_dict(self) -> dict:
        return {
            "requirement": self.requirement.requirement_text,
            "category": self.requirement.category.value,
            "importance": self.requirement.importance.value,
            "required": self.requirement.required,
            "status": self.status.value,
            "evidence": self.evidence,
            "reason": self.reason,
        }


def _evaluate_skill(req: JobRequirement, ctx: ProfileContext) -> RequirementEvaluation:
    name = req.skill_name or req.requirement_text
    found = lookup_skill(ctx, name)
    if found is None:
        return RequirementEvaluation(req, MatchStatus.MISSING, reason="Not found in career profile.")
    if found.verified:
        return RequirementEvaluation(req, MatchStatus.MATCHED, evidence=found.sources)
    return RequirementEvaluation(
        req, MatchStatus.PARTIAL, evidence=found.sources,
        reason="Appears in profile but is not marked verified.",
    )


def _evaluate_experience(req: JobRequirement, ctx: ProfileContext) -> RequirementEvaluation:
    total_years = ctx.profile.years_of_experience
    if req.years_required is None:
        # No parseable year figure -- fall back to keyword overlap against
        # experience descriptions/bullets.
        return _evaluate_text_overlap(req, ctx, [
            (exp.description or "") + " " + " ".join(b.bullet for b in exp.bullets) for exp in ctx.experiences
        ], source_label="Experience")

    if total_years is None:
        return RequirementEvaluation(req, MatchStatus.UNKNOWN, reason="years_of_experience is not set on the profile.")
    if total_years >= req.years_required:
        return RequirementEvaluation(
            req, MatchStatus.MATCHED, evidence=[f"Profile total experience: {total_years} years"],
        )
    if total_years > 0:
        return RequirementEvaluation(
            req, MatchStatus.PARTIAL, evidence=[f"Profile total experience: {total_years} years"],
            reason=f"Requires {req.years_required}+ years; profile shows {total_years}.",
        )
    return RequirementEvaluation(req, MatchStatus.MISSING, reason="No years of experience recorded on the profile.")


def _evaluate_education(req: JobRequirement, ctx: ProfileContext) -> RequirementEvaluation:
    if not ctx.educations:
        return RequirementEvaluation(req, MatchStatus.MISSING, reason="No education records in profile.")

    requirement_tokens = set(normalize_skill(req.education_requirement or req.requirement_text).split())
    best_overlap = 0
    best_edu = None
    for edu in ctx.educations:
        edu_text = f"{edu.degree} {edu.field or ''}"
        edu_tokens = set(normalize_skill(edu_text).split())
        overlap = len(requirement_tokens & edu_tokens)
        if overlap > best_overlap:
            best_overlap = overlap
            best_edu = edu

    if best_edu is None:
        return RequirementEvaluation(req, MatchStatus.MISSING, reason="No matching degree/field found in profile.")
    evidence = [f"Education: {best_edu.degree} in {best_edu.field}, {best_edu.institution}"]
    if best_overlap >= 2:
        return RequirementEvaluation(req, MatchStatus.MATCHED, evidence=evidence)
    return RequirementEvaluation(
        req, MatchStatus.PARTIAL, evidence=evidence, reason="Related education found but not an exact match.",
    )


def _evaluate_certification(req: JobRequirement, ctx: ProfileContext) -> RequirementEvaluation:
    target = normalize_skill(req.requirement_text)
    for cert in ctx.certifications:
        if normalize_skill(cert.name) in target or target in normalize_skill(cert.name):
            status = MatchStatus.MATCHED if cert.verified else MatchStatus.PARTIAL
            return RequirementEvaluation(req, status, evidence=[f"Certification: {cert.name} ({cert.issuer})"])
    return RequirementEvaluation(req, MatchStatus.MISSING, reason="No matching certification in profile.")


def _evaluate_text_overlap(
    req: JobRequirement, ctx: ProfileContext, corpus: list[str], source_label: str
) -> RequirementEvaluation:
    requirement_tokens = {t for t in normalize_skill(req.requirement_text).split() if len(t) > 3}
    if not requirement_tokens:
        return RequirementEvaluation(req, MatchStatus.UNKNOWN, reason="Requirement text too short to evaluate.")

    for text in corpus:
        text_tokens = set(normalize_skill(text).split())
        overlap = requirement_tokens & text_tokens
        if len(overlap) >= max(2, len(requirement_tokens) // 2):
            return RequirementEvaluation(
                req, MatchStatus.PARTIAL, evidence=[f"{source_label} mentions: {', '.join(sorted(overlap))}"],
                reason="Keyword overlap found; not confirmed as a direct, verified match.",
            )
    return RequirementEvaluation(req, MatchStatus.UNKNOWN, reason="No clear textual evidence found either way.")


def _evaluate_responsibility(req: JobRequirement, ctx: ProfileContext) -> RequirementEvaluation:
    corpus = [(exp.description or "") + " " + " ".join(b.bullet for b in exp.bullets) for exp in ctx.experiences]
    corpus += [(p.description or "") + " " + (p.problem or "") + " " + (p.solution or "") for p in ctx.projects]
    return _evaluate_text_overlap(req, ctx, corpus, source_label="Experience/Project")


def _evaluate_location(req: JobRequirement, ctx: ProfileContext) -> RequirementEvaluation:
    profile = ctx.profile
    if not profile.preferred_locations and not profile.remote_preference:
        return RequirementEvaluation(req, MatchStatus.UNKNOWN, reason="No location preference recorded on profile.")

    requirement_text = req.requirement_text.lower()
    if profile.remote_preference and profile.remote_preference.value in ("remote", "flexible") and "remote" in requirement_text:
        return RequirementEvaluation(req, MatchStatus.MATCHED, evidence=[f"Remote preference: {profile.remote_preference.value}"])

    for loc in profile.preferred_locations:
        if loc.lower() in requirement_text or requirement_text in loc.lower():
            return RequirementEvaluation(req, MatchStatus.MATCHED, evidence=[f"Preferred location: {loc}"])

    return RequirementEvaluation(
        req, MatchStatus.UNKNOWN,
        reason="Job location does not clearly match stated preferences; not enough information to call this a mismatch.",
    )


def _evaluate_unassessable(req: JobRequirement, ctx: ProfileContext) -> RequirementEvaluation:
    return RequirementEvaluation(
        req, MatchStatus.UNKNOWN,
        reason="The career profile does not capture this information -- it is never assumed.",
    )


def _evaluate_soft_skill(req: JobRequirement, ctx: ProfileContext) -> RequirementEvaluation:
    corpus = [(exp.description or "") for exp in ctx.experiences]
    corpus += [f"{a.title} {a.description or ''}" for a in ctx.achievements]
    result = _evaluate_text_overlap(req, ctx, corpus, source_label="Experience/Achievement")
    # Soft skills are inherently hard to verify from structured data --
    # never call one confidently "missing" from silence alone.
    if result.status == MatchStatus.MISSING:
        result.status = MatchStatus.UNKNOWN
    return result


_CATEGORY_EVALUATORS = {
    RequirementCategory.TECHNICAL_SKILL: _evaluate_skill,
    RequirementCategory.EXPERIENCE: _evaluate_experience,
    RequirementCategory.EDUCATION: _evaluate_education,
    RequirementCategory.CERTIFICATION: _evaluate_certification,
    RequirementCategory.RESPONSIBILITY: _evaluate_responsibility,
    RequirementCategory.LOCATION: _evaluate_location,
    RequirementCategory.WORK_AUTHORIZATION: _evaluate_unassessable,
    RequirementCategory.LANGUAGE: _evaluate_unassessable,
    RequirementCategory.SOFT_SKILL: _evaluate_soft_skill,
    RequirementCategory.OTHER: _evaluate_soft_skill,
}


def evaluate_requirement(req: JobRequirement, ctx: ProfileContext) -> RequirementEvaluation:
    evaluator = _CATEGORY_EVALUATORS.get(req.category, _evaluate_unassessable)
    return evaluator(req, ctx)


# --- Scoring ---------------------------------------------------------------


def _avg_status_score(evals: list[RequirementEvaluation]) -> float:
    if not evals:
        return 1.0
    return sum(_STATUS_SCORE[e.status] for e in evals) / len(evals)


def _keyword_alignment_score(job: Job, ctx: ProfileContext) -> float:
    if not job.keywords:
        return 1.0
    matched = 0
    for keyword in job.keywords:
        if lookup_skill(ctx, keyword) is not None:
            matched += 1
    return min(1.0, matched / len(job.keywords))


def _source_specific_skill_score(evaluations: list[RequirementEvaluation], source_prefix: str) -> float:
    skill_evals = [e for e in evaluations if e.requirement.category == RequirementCategory.TECHNICAL_SKILL]
    if not skill_evals:
        return 1.0
    hits = sum(1 for e in skill_evals if any(ev.startswith(source_prefix) for ev in e.evidence))
    return hits / len(skill_evals)


def _score_components(job: Job, evaluations: list[RequirementEvaluation], ctx: ProfileContext) -> dict[str, float]:
    def by_category(cat, required=None):
        return [
            e for e in evaluations
            if e.requirement.category == cat and (required is None or e.requirement.required == required)
        ]
    other_categories = {
        RequirementCategory.SOFT_SKILL, RequirementCategory.CERTIFICATION, RequirementCategory.RESPONSIBILITY,
        RequirementCategory.LOCATION, RequirementCategory.WORK_AUTHORIZATION, RequirementCategory.LANGUAGE,
        RequirementCategory.OTHER,
    }
    return {
        "required_skills": _avg_status_score(by_category(RequirementCategory.TECHNICAL_SKILL, required=True)),
        "preferred_skills": _avg_status_score(by_category(RequirementCategory.TECHNICAL_SKILL, required=False)),
        "experience": _avg_status_score(by_category(RequirementCategory.EXPERIENCE)),
        "education": _avg_status_score(by_category(RequirementCategory.EDUCATION)),
        "technical_alignment": _keyword_alignment_score(job, ctx),
        "projects": _source_specific_skill_score(evaluations, "Project:"),
        "research": _source_specific_skill_score(evaluations, "Research:"),
        "other_requirements": _avg_status_score([e for e in evaluations if e.requirement.category in other_categories]),
    }


def score_to_recommendation(score: int, thresholds: dict[str, int]) -> Recommendation:
    if score >= thresholds["apply"]:
        return Recommendation.APPLY
    if score >= thresholds["maybe"]:
        return Recommendation.MAYBE
    return Recommendation.SKIP


def _build_strength_line(e: RequirementEvaluation) -> str:
    return e.requirement.skill_name or e.requirement.requirement_text


def _build_weakness_line(e: RequirementEvaluation) -> str:
    return e.requirement.skill_name or e.requirement.requirement_text


def _fallback_reasoning_summary(
    job: Job, score: int, recommendation: Recommendation, strengths: list[str], weaknesses: list[str], critical_gaps: list[str]
) -> str:
    parts = [f"Overall alignment score: {score}/100 ({recommendation.value})."]
    if strengths:
        parts.append("Strong matches: " + ", ".join(strengths[:5]) + ".")
    if weaknesses:
        parts.append("Gaps: " + ", ".join(weaknesses[:5]) + ".")
    if critical_gaps:
        parts.append("Critical gap(s) forced a skip recommendation: " + ", ".join(critical_gaps) + ".")
    return " ".join(parts)


def _generate_explanation(
    job: Job, score: int, recommendation: Recommendation, strengths: list[str], weaknesses: list[str], critical_gaps: list[str]
) -> str:
    fallback = _fallback_reasoning_summary(job, score, recommendation, strengths, weaknesses, critical_gaps)
    try:
        client = get_ai_client()
        model = get_ai_model()
    except AIConfigurationError:
        return fallback

    payload = (
        f"Score: {score}/100\nRecommendation: {recommendation.value}\n"
        f"Strengths: {strengths}\nGaps: {weaknesses}\nCritical gaps: {critical_gaps}"
    )
    try:
        completion = client.chat.completions.parse(
            model=model,
            messages=[
                {"role": "system", "content": JOB_MATCH_EXPLANATION_PROMPT_V1},
                {"role": "user", "content": payload},
            ],
            response_format=MatchExplanationResult,
        )
        parsed = completion.choices[0].message.parsed
        if parsed is None:
            return fallback
        return parsed.reasoning_summary
    except Exception as exc:
        logger.warning("match explanation AI call failed, using fallback summary: %s", exc.__class__.__name__)
        return fallback


def _advance_status_to_matched(job: Job) -> None:
    """compute_match() runs every time a match score is (re)computed --
    including internally, e.g. cv_customization_service calling it twice
    to report a CV's match_score_before/after. Unconditionally setting
    status=MATCHED there would silently regress a job the user had
    already manually moved further along (e.g. shortlisted, preparing) --
    exactly the kind of automatic status change Step 6 exists to prevent
    (a job must never be advanced or reset by something other than an
    explicit, meaningful step). Only ever moves status forward from an
    earlier pipeline stage, never backward, and never touches a
    terminal/user-decided status (withdrawn/closed/rejected/archived/skipped)."""

    if job.status not in _JOB_STAGE_ORDER:
        return
    if _JOB_STAGE_ORDER.index(job.status) < _JOB_STAGE_ORDER.index(JobStatus.MATCHED):
        job.status = JobStatus.MATCHED


def compute_match(
    db: Session,
    job: Job,
    weights: dict[str, float] | None = None,
    thresholds: dict[str, int] | None = None,
    use_ai_explanation: bool = True,
) -> JobMatch:
    weights = weights or DEFAULT_WEIGHTS
    thresholds = thresholds or DEFAULT_RECOMMENDATION_THRESHOLDS

    requirements = db.execute(select(JobRequirement).where(JobRequirement.job_id == job.id)).scalars().all()
    if not requirements:
        raise MatchInputError("This job has no extracted requirements yet -- analyze it first.")

    profile = get_default_profile(db)
    if profile is None:
        raise MatchInputError("No career profile exists yet -- create one before matching.")
    ctx = get_relevant_career_data(db, profile.id)

    evaluations = [evaluate_requirement(req, ctx) for req in requirements]
    components = _score_components(job, evaluations, ctx)
    overall = sum(weights[key] * components[key] for key in weights)
    overall_score = max(0, min(100, round(overall * 100)))

    critical_gap_evals = [
        e for e in evaluations if e.requirement.importance == RequirementImportance.CRITICAL and e.status == MatchStatus.MISSING
    ]
    critical_gaps = [_build_weakness_line(e) for e in critical_gap_evals]

    recommendation = score_to_recommendation(overall_score, thresholds)
    if critical_gaps:
        recommendation = Recommendation.SKIP

    matched = [e for e in evaluations if e.status == MatchStatus.MATCHED]
    partial = [e for e in evaluations if e.status == MatchStatus.PARTIAL]
    missing = [e for e in evaluations if e.status == MatchStatus.MISSING]
    unknown = [e for e in evaluations if e.status == MatchStatus.UNKNOWN]

    strengths = [_build_strength_line(e) for e in matched][:8]
    weaknesses = [_build_weakness_line(e) for e in (missing + partial)][:8]

    reasoning_summary = (
        _generate_explanation(job, overall_score, recommendation, strengths, weaknesses, critical_gaps)
        if use_ai_explanation
        else _fallback_reasoning_summary(job, overall_score, recommendation, strengths, weaknesses, critical_gaps)
    )

    existing = db.execute(select(JobMatch).where(JobMatch.job_id == job.id)).scalar_one_or_none()
    match = existing or JobMatch(job_id=job.id)
    match.overall_score = overall_score
    match.recommendation = recommendation
    match.matched_requirements = [e.to_dict() for e in matched]
    match.partial_requirements = [e.to_dict() for e in partial]
    match.missing_requirements = [e.to_dict() for e in missing]
    match.unknown_requirements = [e.to_dict() for e in unknown]
    match.critical_gaps = critical_gaps
    match.strengths = strengths
    match.weaknesses = weaknesses
    match.reasoning_summary = reasoning_summary
    match.score_components = {key: round(value * 100) for key, value in components.items()}
    match.algorithm_version = MATCH_ALGORITHM_VERSION

    if not existing:
        db.add(match)

    _advance_status_to_matched(job)

    db.commit()
    db.refresh(match)
    logger.info("job id=%s matched, score=%d recommendation=%s", job.id, overall_score, recommendation.value)
    return match
