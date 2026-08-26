"""Builds the CVChange audit trail at generation time, and reads it back
(plus a few direct diffs) to answer GET /cvs/{id}/comparison. Nothing here
calls the LLM -- a comparison is just a description of decisions already
made deterministically or already recorded.

Experience, projects, and section order are deliberately absent from this
audit trail: the full profile is always included, verbatim, on every
tailored CV (see cv_customization_service.assemble_cv_content), so there
is never an "added"/"removed"/"reworded" experience or project, or a
reordered section, to report. Only the two things that do vary per job --
which skills are surfaced, and the summary wording -- are tracked."""

from app.models.cv_change import CVChange
from app.models.cv_version import CVVersion
from app.models.enums import CVChangeType, CVSectionType
from app.schemas.cv import CVComparisonEntry, CVComparisonResponse
from app.schemas.cv_generation import CVPlan
from app.services.job_matching_service import ProfileContext, normalize_skill


def build_cv_changes(plan: CVPlan, sanitized: dict, ctx: ProfileContext) -> list[CVChange]:
    changes: list[CVChange] = []
    profile = ctx.profile

    new_summary = sanitized.get("summary", "")
    if (profile.current_summary or "").strip() != (new_summary or "").strip():
        changes.append(CVChange(
            change_type=CVChangeType.REWRITTEN, section=CVSectionType.SUMMARY,
            original_text=profile.current_summary, customized_text=new_summary,
            reason="Tailored to the target role.",
        ))

    shown_skills = {normalize_skill(s) for cat in sanitized["skills"] for s in cat["skills"]}
    priority = {normalize_skill(s) for s in plan.priority_skills}
    for name in ctx.skill_index:
        if name in shown_skills:
            if name in priority:
                changes.append(CVChange(
                    change_type=CVChangeType.EMPHASIZED, section=CVSectionType.SKILLS,
                    customized_text=name, reason="Matches a job requirement.",
                ))
        else:
            changes.append(CVChange(
                change_type=CVChangeType.DE_EMPHASIZED, section=CVSectionType.SKILLS,
                original_text=name, reason="Not relevant to this job.",
            ))

    return changes


def build_comparison_response(cv_version: CVVersion, changes: list[CVChange]) -> CVComparisonResponse:
    added_skills = [c.customized_text for c in changes if c.section == CVSectionType.SKILLS and c.change_type == CVChangeType.EMPHASIZED]
    de_emphasized = [c.original_text for c in changes if c.section == CVSectionType.SKILLS and c.change_type == CVChangeType.DE_EMPHASIZED]
    summary_changed = any(c.section == CVSectionType.SUMMARY and c.change_type == CVChangeType.REWRITTEN for c in changes)

    return CVComparisonResponse(
        cv_id=cv_version.id,
        job_id=cv_version.job_id,
        match_score_before=cv_version.match_score_before,
        match_score_after=cv_version.match_score_after,
        added_skills=added_skills,
        removed_skills=[],
        reordered_skills=added_skills,
        de_emphasized_skills=de_emphasized,
        # Experience/projects are always included in full and never
        # reordered (see module docstring), so these are permanently
        # empty -- kept in the response shape for API stability.
        added_projects=[],
        removed_projects=[],
        summary_changed=summary_changed,
        section_order=[],
        changes=[
            CVComparisonEntry(
                change_type=c.change_type.value, section=c.section.value,
                original_text=c.original_text, customized_text=c.customized_text,
                source_id=c.source_id, reason=c.reason,
            )
            for c in changes
        ],
    )
