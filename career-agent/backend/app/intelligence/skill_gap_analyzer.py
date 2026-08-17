"""Skill demand + gap analysis (spec sections 16-18). Deterministic --
purely counting/ranking what's already stored (JobRequirement rows,
Career Profile skills). Never invents a skill the user doesn't have, and
never claims a skill is required to succeed -- only that it appears
frequently in analyzed jobs.
"""

from collections import Counter, defaultdict
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.enums import RequirementCategory, RequirementImportance
from app.models.job import Job
from app.models.job_requirement import JobRequirement
from app.models.profile import CareerProfile
from app.services.job_matching_service import normalize_skill, skills_equivalent

_IMPORTANCE_WEIGHT = {
    RequirementImportance.CRITICAL: 1.0,
    RequirementImportance.HIGH: 0.75,
    RequirementImportance.MEDIUM: 0.5,
    RequirementImportance.LOW: 0.25,
}


@dataclass
class SkillGapEntry:
    skill: str
    demand_count: int
    demand_ratio: float
    importance_score: float
    relevance_score: float
    priority_score: float
    priority: str  # "high" | "medium" | "low"
    has_skill: bool
    current_level: str | None
    reason: str
    suggested_next_step: str | None = None


def _priority_bucket(score: float) -> str:
    if score >= 0.5:
        return "high"
    if score >= 0.25:
        return "medium"
    return "low"


def analyze_skill_gaps(db: Session, profile: CareerProfile | None, top_n: int = 20) -> list[SkillGapEntry]:
    """Analyzes every job with extracted requirements (spec section 16's
    "last N analyzed jobs"), not just ones you applied to -- this is
    about market demand, distinct from Step 6's application-outcome
    analytics."""

    jobs = db.execute(select(Job).where(Job.extracted_at.isnot(None))).scalars().all()
    total_jobs = len(jobs)
    if total_jobs == 0:
        return []

    target_role_words = set()
    if profile and profile.target_roles:
        for role in profile.target_roles:
            target_role_words.update(role.lower().split())

    job_ids_by_role_relevance = set()
    for job in jobs:
        title_words = set((job.title or "").lower().split())
        if not target_role_words or (title_words & target_role_words):
            job_ids_by_role_relevance.add(job.id)

    requirements = db.execute(
        select(JobRequirement).where(
            JobRequirement.job_id.in_([j.id for j in jobs]),
            JobRequirement.category == RequirementCategory.TECHNICAL_SKILL,
            JobRequirement.skill_name.isnot(None),
        )
    ).scalars().all()

    demand: Counter[str] = Counter()
    importance_sum: dict[str, float] = defaultdict(float)
    relevant_demand: Counter[str] = Counter()

    for req in requirements:
        demand[req.skill_name] += 1
        importance_sum[req.skill_name] += _IMPORTANCE_WEIGHT.get(req.importance, 0.5)
        if req.job_id in job_ids_by_role_relevance:
            relevant_demand[req.skill_name] += 1

    profile_skills = list(profile.skills) if profile else []

    def _skill_status(skill_name: str) -> tuple[bool, str | None]:
        for ps in profile_skills:
            if skills_equivalent(skill_name, ps.name):
                return True, ps.proficiency.value if ps.proficiency else None
        return False, None

    entries: list[SkillGapEntry] = []
    for skill_name, count in demand.most_common():
        demand_ratio = count / total_jobs
        importance_score = importance_sum[skill_name] / count
        relevance_score = (relevant_demand[skill_name] / count) if count else 1.0
        if not target_role_words:
            relevance_score = 1.0  # no target roles configured -- can't discount relevance

        priority_score = round(demand_ratio * importance_score * relevance_score, 3)
        has_skill, level = _skill_status(skill_name)

        reason = f"Appears in {count}/{total_jobs} analyzed jobs ({round(demand_ratio * 100)}%)."
        entry = SkillGapEntry(
            skill=skill_name, demand_count=count, demand_ratio=round(demand_ratio, 3),
            importance_score=round(importance_score, 2), relevance_score=round(relevance_score, 2),
            priority_score=priority_score, priority=_priority_bucket(priority_score),
            has_skill=has_skill, current_level=level, reason=reason,
        )
        if not has_skill:
            entry.suggested_next_step = (
                f"Consider learning {skill_name} -- it appears in {round(demand_ratio * 100)}% of analyzed target jobs."
            )
        entries.append(entry)

    return entries[:top_n]


def missing_skill_gaps(entries: list[SkillGapEntry]) -> list[SkillGapEntry]:
    return [e for e in entries if not e.has_skill]
