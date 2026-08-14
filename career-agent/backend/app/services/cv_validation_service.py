"""Deterministic validation of generated CV content against the Career
Profile. This runs regardless of how carefully the prompts were written --
the LLM is never trusted to grade its own work. Every check here is a
plain data comparison, not a judgment call.
"""

import re

from app.ai.cv_structured_outputs import CVContentOutput
from app.schemas.cv_generation import ValidationIssue
from app.services.job_matching_service import ProfileContext, lookup_skill, normalize_skill

NUMBER_PATTERN = re.compile(r"\d+(?:\.\d+)?%?x?\b")


def _numbers_in(text: str) -> set[str]:
    return set(NUMBER_PATTERN.findall(text.lower()))


def _matching_terms(text: str, candidate_terms: set[str]) -> set[str]:
    """Which of `candidate_terms` (already normalized) appear as a
    normalized substring inside `text`."""
    normalized_text = f" {normalize_skill(text)} "
    return {term for term in candidate_terms if term and f" {term} " in normalized_text}


def validate_skill_categories(content: CVContentOutput, ctx: ProfileContext) -> tuple[list[ValidationIssue], list]:
    """Returns (issues, sanitized_skill_categories) -- unsupported skill
    names are stripped from the sanitized output rather than silently kept."""

    issues: list[ValidationIssue] = []
    sanitized = []
    for cat in content.skill_categories:
        kept = []
        for skill in cat.skills:
            evidence = lookup_skill(ctx, skill)
            if evidence is None:
                issues.append(ValidationIssue(
                    code="UNSUPPORTED_SKILL",
                    message=f"'{skill}' does not exist in the career profile and was removed.",
                    section="skills",
                ))
            else:
                kept.append(skill)
        if kept:
            sanitized.append({"category": cat.category, "skills": kept})
    return issues, sanitized


def validate_bullets(
    content_bullets: list,
    valid_source_ids: set[int],
    original_text_by_id: dict[int, str],
    known_technologies_by_id: dict[int, set[str]],
    ctx: ProfileContext,
    section: str,
    watch_terms: list[str] = (),
) -> tuple[list[ValidationIssue], list]:
    """Validates a list of RewrittenBullet against their real source rows.
    Returns (issues, sanitized_bullets) where sanitized_bullets is a list
    of {source_bullet_id, text} -- unsupported metrics/technologies fall
    back to the verbatim original text rather than being dropped outright,
    since the underlying fact itself is still true and worth keeping.

    `watch_terms` should include the job's requirement skill names.
    Without them, "introduced technology" can only be detected when the
    term happens to already be a *known* profile skill used elsewhere --
    a wholly invented technology that appears nowhere else in the profile
    (e.g. the job wants AWS, the profile has zero AWS mentions) would
    otherwise slip through undetected."""

    issues: list[ValidationIssue] = []
    sanitized = []
    watch_normalized = {normalize_skill(t) for t in watch_terms if normalize_skill(t)}

    for bullet in content_bullets:
        source_id = bullet.source_bullet_id
        if source_id not in valid_source_ids:
            issues.append(ValidationIssue(
                code="UNSUPPORTED_BULLET_SOURCE",
                message=f"Rewritten bullet references source id {source_id}, which is not part of "
                        f"the selected career profile item -- discarded.",
                section=section,
            ))
            continue

        original = original_text_by_id[source_id]
        rewritten = bullet.rewritten_text

        original_numbers = _numbers_in(original)
        rewritten_numbers = _numbers_in(rewritten)
        introduced_numbers = rewritten_numbers - original_numbers

        candidate_terms = set(ctx.skill_index.keys()) | watch_normalized | {
            normalize_skill(t) for t in known_technologies_by_id.get(source_id, set())
        }
        original_tech = _matching_terms(original, candidate_terms) | {
            normalize_skill(t) for t in known_technologies_by_id.get(source_id, set())
        }
        rewritten_tech = _matching_terms(rewritten, candidate_terms)
        introduced_tech = rewritten_tech - original_tech

        if introduced_numbers:
            issues.append(ValidationIssue(
                code="UNSUPPORTED_METRIC",
                message=f"Rewrite of bullet {source_id} introduced number(s) {sorted(introduced_numbers)} "
                        f"not present in the original -- reverted to original text.",
                section=section,
            ))
            rewritten = original
        elif introduced_tech:
            issues.append(ValidationIssue(
                code="UNSUPPORTED_TECHNOLOGY",
                message=f"Rewrite of bullet {source_id} introduced technology/skill {sorted(introduced_tech)} "
                        f"not present in the original -- reverted to original text.",
                section=section,
            ))
            rewritten = original

        sanitized.append({"source_bullet_id": source_id, "text": rewritten})

    return issues, sanitized


def validate_summary(summary: str, ctx: ProfileContext, watch_terms: list[str]) -> list[ValidationIssue]:
    """The summary can't be mechanically 'sanitized' the way a bullet can
    (there's no single source row to fall back to), so an unsupported claim
    here is reported as a warning rather than silently rewritten -- callers
    decide whether that blocks 'validated' status.

    `watch_terms` should be the job's requirement skill names -- the exact
    terms an LLM would be tempted to slip into the summary "because the job
    mentions them" (explicitly forbidden). Checking the summary against the
    profile's own vocabulary can't catch this: every term found that way is
    supported by construction. What needs checking is whether the *job's*
    vocabulary leaked in unsupported."""

    issues: list[ValidationIssue] = []
    normalized_summary = f" {normalize_skill(summary)} "
    seen = set()
    for term in watch_terms:
        normalized_term = normalize_skill(term)
        if not normalized_term or normalized_term in seen:
            continue
        seen.add(normalized_term)
        if f" {normalized_term} " in normalized_summary and lookup_skill(ctx, term) is None:
            issues.append(ValidationIssue(
                code="UNSUPPORTED_TECHNOLOGY_IN_SUMMARY",
                message=f"Summary mentions '{term}', which is not in the career profile.",
                section="summary",
            ))
    return issues
