from app.services.answer_validation_service import validate_generated_text
from app.services.job_matching_service import get_relevant_career_data


def test_valid_text_with_supported_claims_passes(client, rich_profile, db_session):
    ctx = get_relevant_career_data(db_session, rich_profile["profile"]["id"])
    text = "I have hands-on experience with PyTorch, developed at Acme AI."
    issues = validate_generated_text(text, ctx, watch_terms=["PyTorch"])
    assert issues == []


def test_unsupported_skill_detected(client, rich_profile, db_session):
    ctx = get_relevant_career_data(db_session, rich_profile["profile"]["id"])
    text = "I have deep experience with AWS and Kubernetes deployments."
    issues = validate_generated_text(text, ctx, watch_terms=["AWS", "Kubernetes"])
    codes = [i.code for i in issues]
    assert "UNSUPPORTED_SKILL" in codes
    assert len([c for c in codes if c == "UNSUPPORTED_SKILL"]) == 2


def test_unsupported_metric_detected(client, rich_profile, db_session):
    ctx = get_relevant_career_data(db_session, rich_profile["profile"]["id"])
    text = "I improved throughput by 250% in my last role."
    issues = validate_generated_text(text, ctx, watch_terms=[])
    assert any(i.code == "UNSUPPORTED_METRIC" for i in issues)


def test_metric_present_in_profile_evidence_is_allowed(client, rich_profile, db_session):
    ctx = get_relevant_career_data(db_session, rich_profile["profile"]["id"])
    # rich_profile's project result metric is "+6.2% Dice score"
    text = "On this project I achieved a 6.2% improvement in segmentation accuracy."
    issues = validate_generated_text(text, ctx, watch_terms=[])
    assert not any(i.code == "UNSUPPORTED_METRIC" for i in issues)


def test_unsupported_company_admiration_claim_detected(client, rich_profile, db_session):
    ctx = get_relevant_career_data(db_session, rich_profile["profile"]["id"])
    text = "I admire your company's innovative culture and want to join your team."
    issues = validate_generated_text(text, ctx, watch_terms=[], job_description="We build computer vision systems.")
    assert any(i.code == "UNSUPPORTED_COMPANY_CLAIM" for i in issues)


def test_company_claim_grounded_in_job_description_is_allowed(client, rich_profile, db_session):
    ctx = get_relevant_career_data(db_session, rich_profile["profile"]["id"])
    text = "I am drawn to your innovative culture of building computer vision systems."
    issues = validate_generated_text(
        text, ctx, watch_terms=[],
        job_description="We are proud of our innovative culture of building computer vision systems.",
    )
    assert not any(i.code == "UNSUPPORTED_COMPANY_CLAIM" for i in issues)


def test_verified_skill_variant_not_flagged(client, rich_profile, db_session):
    ctx = get_relevant_career_data(db_session, rich_profile["profile"]["id"])
    text = "I have strong experience with the PyTorch framework."
    issues = validate_generated_text(text, ctx, watch_terms=["PyTorch"])
    assert issues == []
