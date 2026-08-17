"""CV content analysis (spec sections 13-15). Never invents anything --
"missing" only ever means "present in your verified Career Profile but
not currently on this CV," phrased as "potential improvement, if
supported," never as an instruction to fabricate a claim.

Unsupported-claim detection is NOT re-implemented here: cv_validation_service
already runs deterministic hallucination checks at generation time and
stores the result on CVVersion.warnings -- this module just surfaces
that existing, already-computed field rather than duplicating the logic.
"""

from dataclasses import dataclass, field

from app.models.cv_version import CVVersion
from app.models.job import Job
from app.models.job_match import JobMatch
from app.models.profile import CareerProfile
from app.services.job_matching_service import skills_equivalent


@dataclass
class ProfileCVGapReport:
    missing_skills: list[str] = field(default_factory=list)
    missing_projects: list[str] = field(default_factory=list)
    missing_achievements: list[str] = field(default_factory=list)
    duplicate_bullets: list[str] = field(default_factory=list)
    unsupported_claims: list[str] = field(default_factory=list)  # from CVVersion.warnings
    suggestions: list[str] = field(default_factory=list)


def _flatten_cv_skills(cv_version: CVVersion) -> set[str]:
    names = set()
    for category in cv_version.skills or []:
        for skill in category.get("skills", []):
            names.add(skill)
    return names


def _all_cv_bullets(cv_version: CVVersion) -> list[str]:
    bullets = []
    for entry in (cv_version.experience or []) + (cv_version.projects or []) + (cv_version.research or []):
        for b in entry.get("bullets", []):
            text = b.get("text")
            if text:
                bullets.append(text)
    return bullets


def analyze_profile_vs_cv(profile: CareerProfile, cv_version: CVVersion) -> ProfileCVGapReport:
    report = ProfileCVGapReport()

    cv_skill_names = _flatten_cv_skills(cv_version)
    for skill in profile.skills:
        if not any(skills_equivalent(skill.name, cv_name) for cv_name in cv_skill_names):
            report.missing_skills.append(skill.name)

    cv_project_ids = {p.get("project_id") for p in (cv_version.projects or [])}
    for project in profile.projects:
        if project.id not in cv_project_ids:
            report.missing_projects.append(project.name)

    cv_achievement_texts = {a.get("text") for a in (cv_version.achievements or [])}
    for achievement in profile.achievements:
        if achievement.title not in cv_achievement_texts:
            report.missing_achievements.append(achievement.title)

    bullets = _all_cv_bullets(cv_version)
    seen = set()
    for text in bullets:
        normalized = text.strip().lower()
        if normalized in seen:
            report.duplicate_bullets.append(text)
        seen.add(normalized)

    report.unsupported_claims = list(cv_version.warnings or [])

    for skill in report.missing_skills[:5]:
        report.suggestions.append(f"Potential improvement: include {skill} if it's relevant to the roles you're targeting -- it's in your Career Profile but not on this CV.")
    if report.duplicate_bullets:
        report.suggestions.append(f"{len(report.duplicate_bullets)} bullet(s) appear more than once -- consider consolidating.")

    return report


@dataclass
class JobCVGapReport:
    matched: list[str] = field(default_factory=list)
    partial: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    keyword_coverage: float | None = None
    missing_keywords: list[str] = field(default_factory=list)
    supportable_missing_keywords: list[str] = field(default_factory=list)


def analyze_job_cv_gap(job: Job, cv_version: CVVersion, job_match: JobMatch | None, profile: CareerProfile | None = None) -> JobCVGapReport:
    """Job description -> CV gap (spec section 14) -- reuses JobMatch's
    own matched/partial/missing requirement evaluations directly, since
    that's already exactly this computation; adds keyword coverage
    (spec section 15) on top."""

    report = JobCVGapReport()
    if job_match is not None:
        report.matched = [m.get("requirement") for m in job_match.matched_requirements]
        report.partial = [m.get("requirement") for m in job_match.partial_requirements]
        report.missing = [m.get("requirement") for m in job_match.missing_requirements]

    if job.keywords:
        cv_text_words = set()
        for text in _all_cv_bullets(cv_version):
            cv_text_words.update(text.lower().split())
        cv_text_words.update(w.lower() for w in _flatten_cv_skills(cv_version))
        if cv_version.summary:
            cv_text_words.update(cv_version.summary.lower().split())

        present = [kw for kw in job.keywords if kw.lower() in cv_text_words]
        missing = [kw for kw in job.keywords if kw.lower() not in cv_text_words]
        report.keyword_coverage = round(len(present) / len(job.keywords), 3) if job.keywords else None
        report.missing_keywords = missing

        if profile is not None:
            profile_skill_names = [s.name for s in profile.skills]
            report.supportable_missing_keywords = [
                kw for kw in missing if any(skills_equivalent(kw, ps) for ps in profile_skill_names)
            ]

    return report
