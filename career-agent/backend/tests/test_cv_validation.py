from app.services.cv_validation_service import (
    is_same_text,
    normalize_typography,
    validate_bullet_rewrite,
    validate_summary,
)
from app.services.job_matching_service import get_relevant_career_data, normalize_skill


# --- summary validation against job-required terms --------------------------


def test_summary_flags_unsupported_job_term(client, rich_profile, db_session):
    ctx = get_relevant_career_data(db_session, rich_profile["profile"]["id"])
    issues = validate_summary("Experienced engineer skilled in AWS and PyTorch.", ctx, watch_terms=["AWS", "PyTorch"])
    codes = [i.code for i in issues]
    assert "UNSUPPORTED_TECHNOLOGY_IN_SUMMARY" in codes
    # PyTorch is verified in the profile, so it must not be flagged
    assert not any("PyTorch" in i.message for i in issues)


def test_summary_with_only_supported_terms_passes(client, rich_profile, db_session):
    ctx = get_relevant_career_data(db_session, rich_profile["profile"]["id"])
    issues = validate_summary("Experienced engineer skilled in PyTorch.", ctx, watch_terms=["PyTorch"])
    assert issues == []


# --- bullet rewrite validation ----------------------------------------------
#
# These run with no database: a rewrite is judged purely against the
# bullet it came from, plus a vocabulary of terms worth policing.

_VOCABULARY = {normalize_skill(t) for t in ["PyTorch", "TensorFlow", "Kubernetes", "AWS", "Computer Vision"]}
_ORIGINAL = "Worked on a PyTorch training pipeline that cut training time by 30%"


def test_faithful_reword_is_accepted():
    reworded = "Optimized a PyTorch training pipeline, cutting training time by 30%"
    assert validate_bullet_rewrite(_ORIGINAL, reworded, _VOCABULARY) == []


def test_rewrite_may_not_introduce_a_number():
    padded = "Optimized a PyTorch training pipeline, cutting training time by 30% across 12 teams"
    codes = [i.code for i in validate_bullet_rewrite(_ORIGINAL, padded, _VOCABULARY)]
    assert "NEW_METRIC_IN_BULLET" in codes


def test_rewrite_may_not_introduce_a_technology():
    embellished = "Optimized a PyTorch training pipeline on Kubernetes, cutting training time by 30%"
    codes = [i.code for i in validate_bullet_rewrite(_ORIGINAL, embellished, _VOCABULARY)]
    assert "NEW_TECHNOLOGY_IN_BULLET" in codes


def test_rewrite_may_drop_a_technology_the_original_had():
    """The constraint is one-directional. Losing a detail makes a weaker
    bullet, not a false one, so it is not the validator's business."""

    trimmed = "Optimized a training pipeline, cutting training time by 30%"
    assert validate_bullet_rewrite(_ORIGINAL, trimmed, _VOCABULARY) == []


def test_rewrite_may_not_be_padded_out():
    padded = (
        "Architected, owned, and delivered a robust end-to-end mission-critical PyTorch training "
        "pipeline for the entire research organization, cutting training time by 30%"
    )
    codes = [i.code for i in validate_bullet_rewrite(_ORIGINAL, padded, _VOCABULARY)]
    assert "BULLET_REWRITE_PADDED" in codes


def test_empty_rewrite_is_rejected():
    codes = [i.code for i in validate_bullet_rewrite(_ORIGINAL, "   ", _VOCABULARY)]
    assert codes == ["EMPTY_BULLET_REWRITE"]


# --- typographic no-op rewrites ---------------------------------------------
#
# Observed in a real generation: the model returned all 35 bullets with
# ASCII hyphens swapped for U+2011 and nothing else reworded, which a
# plain `!=` read as 12 genuine rewrites.


def test_unicode_hyphen_swap_is_not_a_rewrite():
    assert is_same_text("Implemented real-time monitoring", "Implemented real\u2011time monitoring")


def test_curly_quote_swap_is_not_a_rewrite():
    assert is_same_text('Built "Infinite Writing"', "Built \u201cInfinite Writing\u201d")


def test_trailing_period_alone_is_not_a_rewrite():
    assert is_same_text("Achieved 80.34% mean accuracy", "Achieved 80.34% mean accuracy.")


def test_a_real_reword_is_still_a_rewrite():
    assert not is_same_text("Worked on real-time monitoring", "Built real-time monitoring")


def test_normalize_typography_returns_ascii_punctuation():
    out = normalize_typography("first\u2011order MAML \u2014 \u201cXNLI\u201d\u00a0dataset")
    assert out == 'first-order MAML - "XNLI" dataset'
    assert "\u2011" not in out and "\u201c" not in out
