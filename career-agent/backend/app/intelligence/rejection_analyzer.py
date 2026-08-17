"""Rejection pattern analysis (spec sections 19-21). Purely observational
-- every finding is phrased as "observed pattern," never as a claim that
some factor caused the rejection (spec section 40). `Application.rejection_reason`
is only ever set by the user (see app/models/application.py); this module
only reads it, never infers or writes it.
"""

from collections import Counter, defaultdict
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.intelligence.confidence import confidence_from_sample_size
from app.models.enums import ApplicationStatus
from app.services.analytics_service import applications_with_relations

LOW_MATCH_THRESHOLD = 70


@dataclass
class RejectionAnalysis:
    total_rejected: int
    reason_breakdown: dict[str, int] = field(default_factory=dict)
    low_match_count: int = 0
    low_match_ratio: float | None = None
    by_source: dict[str, int] = field(default_factory=dict)
    by_company: dict[str, int] = field(default_factory=dict)
    by_role: dict[str, int] = field(default_factory=dict)
    by_cv_version: dict[str, int] = field(default_factory=dict)
    observations: list[str] = field(default_factory=list)
    confidence: float = 0.0
    confidence_reason: str = ""


def analyze_rejections(db: Session) -> RejectionAnalysis:
    applications = applications_with_relations(db)
    rejected = [a for a in applications if a.status == ApplicationStatus.REJECTED]
    total = len(rejected)

    confidence, confidence_reason = confidence_from_sample_size(total)
    analysis = RejectionAnalysis(total_rejected=total, confidence=confidence, confidence_reason=confidence_reason)
    if total == 0:
        analysis.observations.append("No rejected applications recorded yet.")
        return analysis

    reason_counts = Counter(a.rejection_reason.value for a in rejected if a.rejection_reason)
    analysis.reason_breakdown = dict(reason_counts.most_common())

    low_match = [a for a in rejected if a.job and a.job.match and a.job.match.overall_score < LOW_MATCH_THRESHOLD]
    analysis.low_match_count = len(low_match)
    analysis.low_match_ratio = round(len(low_match) / total, 3)

    company_counts: Counter[str] = Counter()
    source_counts: Counter[str] = Counter()
    role_counts: Counter[str] = Counter()
    cv_counts: Counter[str] = Counter()
    for a in rejected:
        if a.job and a.job.company:
            company_counts[a.job.company] += 1
        if a.source:
            source_counts[a.source] += 1
        if a.job and a.job.title:
            role_counts[a.job.title] += 1
        if a.cv_version:
            cv_counts[f"{a.cv_version.version_name} [#{a.cv_version.id}]"] += 1

    analysis.by_company = dict(company_counts.most_common())
    analysis.by_source = dict(source_counts.most_common())
    analysis.by_role = dict(role_counts.most_common())
    analysis.by_cv_version = dict(cv_counts.most_common())

    if analysis.low_match_ratio is not None and analysis.low_match_ratio >= 0.5:
        analysis.observations.append(
            f"Observed pattern: {len(low_match)}/{total} rejected applications had a match score below {LOW_MATCH_THRESHOLD}%. "
            "Consider focusing more heavily on roles with stronger requirement alignment."
        )

    if reason_counts:
        top_reason, top_count = reason_counts.most_common(1)[0]
        analysis.observations.append(
            f"'{top_reason}' is the most frequently recorded rejection reason ({top_count}/{total})."
        )

    unknown_count = sum(1 for a in rejected if a.rejection_reason is None)
    if unknown_count:
        analysis.observations.append(
            f"{unknown_count}/{total} rejected applications have no recorded rejection reason -- "
            "recording one (POST /applications/{id}/rejection-reason) would sharpen this analysis."
        )

    return analysis
