from app.services.cv_validation_service import validate_summary
from app.services.job_matching_service import get_relevant_career_data


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
