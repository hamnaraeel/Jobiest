"""Builds the CVChange audit trail at generation time, and reads it back
(plus a few direct diffs) to answer GET /cvs/{id}/comparison. Nothing here
calls the LLM -- a comparison is just a description of decisions already
made deterministically or already recorded.
"""

from app.models.cv_change import CVChange
from app.models.cv_version import CVVersion
from app.models.enums import CVChangeType, CVSectionType, EntityType
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

    for exp in ctx.experiences:
        if exp.id not in plan.selected_experience_ids:
            changes.append(CVChange(
                change_type=CVChangeType.REMOVED, section=CVSectionType.EXPERIENCE,
                original_text=f"{exp.role} at {exp.company}",
                source_type=EntityType.EXPERIENCE, source_id=str(exp.id),
                reason="Not selected as relevant to this job.",
            ))
            continue

        changes.append(CVChange(
            change_type=CVChangeType.ADDED, section=CVSectionType.EXPERIENCE,
            customized_text=f"{exp.role} at {exp.company}",
            source_type=EntityType.EXPERIENCE, source_id=str(exp.id),
            reason="Relevant to job requirements.",
        ))
        included = {b["source_bullet_id"]: b["text"] for b in sanitized["experience"].get(exp.id, [])}
        for bullet in exp.bullets:
            if bullet.id not in included:
                changes.append(CVChange(
                    change_type=CVChangeType.REMOVED, section=CVSectionType.EXPERIENCE,
                    original_text=bullet.bullet,
                    source_type=EntityType.EXPERIENCE_BULLET, source_id=str(bullet.id),
                    reason="Not relevant to this job.",
                ))
            elif included[bullet.id] != bullet.bullet:
                changes.append(CVChange(
                    change_type=CVChangeType.REWRITTEN, section=CVSectionType.EXPERIENCE,
                    original_text=bullet.bullet, customized_text=included[bullet.id],
                    source_type=EntityType.EXPERIENCE_BULLET, source_id=str(bullet.id),
                    reason="Reworded for relevance to this job.",
                ))

    for proj in ctx.projects:
        if proj.id not in plan.selected_project_ids:
            changes.append(CVChange(
                change_type=CVChangeType.REMOVED, section=CVSectionType.PROJECTS,
                original_text=proj.name,
                source_type=EntityType.PROJECT, source_id=str(proj.id),
                reason="Not selected as relevant to this job.",
            ))
            continue

        changes.append(CVChange(
            change_type=CVChangeType.ADDED, section=CVSectionType.PROJECTS,
            customized_text=proj.name,
            source_type=EntityType.PROJECT, source_id=str(proj.id),
            reason="Relevant to job requirements.",
        ))
        included = {b["source_bullet_id"]: b["text"] for b in sanitized["projects"].get(proj.id, [])}
        for result in proj.results:
            # Matches cv_customization_service's validation baseline: a
            # ProjectResult's full "original text" is description + metric
            # combined, not description alone.
            original_result_text = f"{result.description} {result.metric or ''}".strip()
            if result.id not in included:
                changes.append(CVChange(
                    change_type=CVChangeType.REMOVED, section=CVSectionType.PROJECTS,
                    original_text=original_result_text,
                    source_type=EntityType.PROJECT_RESULT, source_id=str(result.id),
                    reason="Not relevant to this job.",
                ))
            elif included[result.id] != original_result_text:
                changes.append(CVChange(
                    change_type=CVChangeType.REWRITTEN, section=CVSectionType.PROJECTS,
                    original_text=original_result_text, customized_text=included[result.id],
                    source_type=EntityType.PROJECT_RESULT, source_id=str(result.id),
                    reason="Reworded for relevance to this job.",
                ))

    canonical_order = [s for s in CVSectionType if s in plan.sections]
    if plan.sections != canonical_order:
        changes.append(CVChange(
            change_type=CVChangeType.REORDERED, section=CVSectionType.SUMMARY,
            customized_text=", ".join(s.value for s in plan.sections),
            reason="Section order tailored to emphasize the most job-relevant content first.",
        ))

    return changes


def build_comparison_response(cv_version: CVVersion, changes: list[CVChange]) -> CVComparisonResponse:
    added_skills = [c.customized_text for c in changes if c.section == CVSectionType.SKILLS and c.change_type == CVChangeType.EMPHASIZED]
    de_emphasized = [c.original_text for c in changes if c.section == CVSectionType.SKILLS and c.change_type == CVChangeType.DE_EMPHASIZED]
    added_projects = [c.customized_text for c in changes if c.section == CVSectionType.PROJECTS and c.change_type == CVChangeType.ADDED]
    removed_projects = [
        c.original_text for c in changes
        if c.section == CVSectionType.PROJECTS and c.change_type == CVChangeType.REMOVED and c.source_type == EntityType.PROJECT
    ]
    summary_changed = any(c.section == CVSectionType.SUMMARY and c.change_type == CVChangeType.REWRITTEN for c in changes)
    section_order_change = next((c for c in changes if c.change_type == CVChangeType.REORDERED), None)

    return CVComparisonResponse(
        cv_id=cv_version.id,
        job_id=cv_version.job_id,
        match_score_before=cv_version.match_score_before,
        match_score_after=cv_version.match_score_after,
        added_skills=added_skills,
        removed_skills=[],
        reordered_skills=added_skills,
        de_emphasized_skills=de_emphasized,
        added_projects=added_projects,
        removed_projects=removed_projects,
        summary_changed=summary_changed,
        section_order=section_order_change.customized_text.split(", ") if section_order_change else [],
        changes=[
            CVComparisonEntry(
                change_type=c.change_type.value, section=c.section.value,
                original_text=c.original_text, customized_text=c.customized_text,
                source_id=c.source_id, reason=c.reason,
            )
            for c in changes
        ],
    )
