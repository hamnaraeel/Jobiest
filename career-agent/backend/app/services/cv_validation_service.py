"""Deterministic validation of generated CV content against the Career
Profile. This runs regardless of how carefully the prompts were written --
the LLM is never trusted to grade its own work. Every check here is a
plain data comparison, not a judgment call.
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
