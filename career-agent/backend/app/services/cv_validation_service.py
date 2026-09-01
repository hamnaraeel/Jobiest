"""Deterministic validation of generated CV content against the Career
Profile. This runs regardless of how carefully the prompts were written --
the LLM is never trusted to grade its own work. Every check here is a
plain data comparison, not a judgment call.

Bullet rewriting (see cv_prompts.CV_BULLET_REWRITE_PROMPT_V1) is allowed
to change a bullet's wording to match a job description, but never its
facts. validate_bullet_rewrite() is what actually enforces that: the
prompt's "do not invent a metric or a technology" instructions are
guidance, and this is the check that makes them true regardless of
whether the model followed them.
"""

import re

from app.schemas.cv_generation import ValidationIssue
from app.services.job_matching_service import ProfileContext, lookup_skill, normalize_skill

NUMBER_PATTERN = re.compile(r"\d+(?:\.\d+)?%?x?\b")


def numbers_in(text: str) -> set[str]:
    return set(NUMBER_PATTERN.findall(text.lower()))


def matching_terms(text: str, candidate_terms: set[str]) -> set[str]:
    """Which of `candidate_terms` (already normalized) appear as a
    normalized substring inside `text`."""
    normalized_text = f" {normalize_skill(text)} "
    return {term for term in candidate_terms if term and f" {term} " in normalized_text}


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


# Word-count headroom a rewrite gets over its original. A faithful
# reword of the same fact lands close to the original length; a rewrite
# that has grown by half is padding, and padding is where unsupported
# scope ("a service" -> "a distributed system serving millions of
# users") hides when it happens to contain neither a new number nor a
# new technology name.
_REWRITE_LENGTH_TOLERANCE = 1.5


def validate_bullet_rewrite(original: str, rewritten: str, vocabulary: set[str]) -> list[ValidationIssue]:
    """Checks one LLM-rewritten bullet against the bullet it came from.
    Unlike the summary -- which has no single source row to fall back to
    -- a bullet always has one, so any issue found here is not a warning
    to surface but a signal to discard the rewrite entirely and keep the
    candidate's original text (see
    cv_customization_service.rewrite_bullets_for_job).

    `vocabulary` is the set of already-normalized technology terms worth
    policing: the candidate's own skills plus the job's requirement
    skill names. It deliberately does not need to be exhaustive -- a
    term the candidate has never claimed and the job never asked for is
    not the kind of keyword an ATS-tailoring model is tempted to insert.
    """

    issues: list[ValidationIssue] = []

    if not rewritten or not rewritten.strip():
        issues.append(ValidationIssue(
            code="EMPTY_BULLET_REWRITE",
            message="Rewritten bullet is empty.",
            section="experience",
        ))
        return issues

    new_numbers = numbers_in(rewritten) - numbers_in(original)
    if new_numbers:
        issues.append(ValidationIssue(
            code="NEW_METRIC_IN_BULLET",
            message=(
                "Rewritten bullet introduces "
                + ", ".join(f"'{n}'" for n in sorted(new_numbers))
                + ", which the original bullet does not contain."
            ),
            section="experience",
        ))

    new_terms = matching_terms(rewritten, vocabulary) - matching_terms(original, vocabulary)
    if new_terms:
        issues.append(ValidationIssue(
            code="NEW_TECHNOLOGY_IN_BULLET",
            message=(
                "Rewritten bullet introduces "
                + ", ".join(f"'{t}'" for t in sorted(new_terms))
                + ", which the original bullet does not mention."
            ),
            section="experience",
        ))

    original_words = len(original.split())
    if original_words and len(rewritten.split()) > original_words * _REWRITE_LENGTH_TOLERANCE:
        issues.append(ValidationIssue(
            code="BULLET_REWRITE_PADDED",
            message=(
                f"Rewritten bullet is {len(rewritten.split())} words against the original's "
                f"{original_words} -- long enough to be carrying content the original does not."
            ),
            section="experience",
        ))

    return issues
