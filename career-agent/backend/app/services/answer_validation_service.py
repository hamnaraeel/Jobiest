"""Deterministic validation for free-form generated text (cover letters,
application answers) against the Career Profile.

Reuses the same primitives as Step 3's cv_validation_service, adapted for
text that isn't a rewrite of one specific source row: there's no single
"original bullet" to diff against, so checks run against the profile's
whole evidence corpus instead of one item's original text.
"""

from app.schemas.cv_generation import ValidationIssue
from app.services.cv_validation_service import matching_terms, numbers_in
from app.services.job_matching_service import ProfileContext, lookup_skill, normalize_skill

# Phrases that claim specific knowledge of/feeling about the company that
# the prompt explicitly forbids unless grounded in supplied job info (spec
# section 15's "I admire your company's innovative culture" example, and
# obvious variants of it).
COMPANY_ADMIRATION_PHRASES = (
    "your company's mission", "your innovative culture", "your company culture",
    "admire your company", "your company's values", "your amazing culture",
    "your cutting-edge", "industry-leading team", "world-class team",
    "your incredible team", "your inspiring mission",
)


def _profile_number_corpus(ctx: ProfileContext) -> set[str]:
    """Every number that legitimately appears anywhere in the profile's
    evidence -- the full set a generated number must belong to, since a
    cover letter/answer can draw a number from any part of the profile,
    not just one bullet."""

    corpus: set[str] = set()
    for exp in ctx.experiences:
        corpus |= numbers_in(exp.description or "")
        for bullet in exp.bullets:
            corpus |= numbers_in(bullet.bullet)
    for proj in ctx.projects:
        corpus |= numbers_in(proj.description or "")
        for result in proj.results:
            corpus |= numbers_in(f"{result.description} {result.metric or ''}")
    for research in ctx.research_items:
        corpus |= numbers_in(" ".join(research.results))
    for achievement in ctx.achievements:
        corpus |= numbers_in(f"{achievement.description or ''} {achievement.metric or ''}")
    if ctx.profile.years_of_experience is not None:
        corpus |= numbers_in(str(ctx.profile.years_of_experience))
    if ctx.profile.salary_expectation:
        corpus |= numbers_in(ctx.profile.salary_expectation)
    return corpus


def validate_generated_text(
    text: str, ctx: ProfileContext, watch_terms: list[str], job_description: str = ""
) -> list[ValidationIssue]:
    """Checks generated free text (a cover letter's full_text, or a single
    application answer) for the same three hallucination shapes Step 3
    checks in CV bullets: unsupported skills/technologies, unsupported
    metrics, plus a cover-letter-specific check for ungrounded company
    claims. Nothing here can "revert to original text" the way a CV
    bullet rewrite can -- callers decide whether issues mean reject or
    warn."""

    issues: list[ValidationIssue] = []

    seen_terms: set[str] = set()
    for term in watch_terms:
        normalized = normalize_skill(term)
        if not normalized or normalized in seen_terms:
            continue
        seen_terms.add(normalized)
        if matching_terms(text, {normalized}) and lookup_skill(ctx, term) is None:
            issues.append(ValidationIssue(
                code="UNSUPPORTED_SKILL",
                message=f"Mentions '{term}', which is not in the verified career profile.",
                section="content",
            ))

    corpus = _profile_number_corpus(ctx)
    for number in numbers_in(text):
        if number not in corpus:
            issues.append(ValidationIssue(
                code="UNSUPPORTED_METRIC",
                message=f"Contains '{number}', which does not match any metric in the verified career profile.",
                section="content",
            ))

    lowered = text.lower()
    lowered_job = job_description.lower()
    for phrase in COMPANY_ADMIRATION_PHRASES:
        if phrase not in lowered:
            continue
        # Job postings describe themselves in first person ("our culture");
        # a cover letter addresses the company in second person ("your
        # culture"). Strip that framing before checking whether the
        # underlying topic is actually grounded in the job's own text.
        topic = phrase
        for prefix in ("your company's ", "admire your company", "your "):
            if topic.startswith(prefix):
                topic = topic[len(prefix):].strip()
                break
        if topic and topic in lowered_job:
            continue
        issues.append(ValidationIssue(
            code="UNSUPPORTED_COMPANY_CLAIM",
            message=f"Contains an unsupported company claim ('{phrase}') not grounded in the "
                    f"supplied job information.",
            section="content",
        ))

    return issues
