from app.ai.cv_structured_outputs import CVContentOutput, SkillCategoryOutput
from app.services.cv_validation_service import validate_skill_categories, validate_summary
from app.services.job_matching_service import get_relevant_career_data


# --- 7: unsupported skill detection -----------------------------------------


def test_unsupported_skill_detected_and_stripped(client, rich_profile, db_session):
    ctx = get_relevant_career_data(db_session, rich_profile["profile"]["id"])
    content = CVContentOutput(
        summary="x",
        skill_categories=[SkillCategoryOutput(category="Cloud", skills=["PyTorch", "AWS"])],
    )
    issues, sanitized = validate_skill_categories(content, ctx)

    assert any(i.code == "UNSUPPORTED_SKILL" and "AWS" in i.message for i in issues)
    assert sanitized == [{"category": "Cloud", "skills": ["PyTorch"]}]


def test_verified_skill_passes_validation(client, rich_profile, db_session):
    ctx = get_relevant_career_data(db_session, rich_profile["profile"]["id"])
    content = CVContentOutput(
        summary="x",
        skill_categories=[SkillCategoryOutput(category="ML/DL", skills=["PyTorch"])],
    )
    issues, sanitized = validate_skill_categories(content, ctx)
    assert issues == []
    assert sanitized == [{"category": "ML/DL", "skills": ["PyTorch"]}]


def test_skill_name_variant_recognized_via_normalization(client, rich_profile, db_session):
    ctx = get_relevant_career_data(db_session, rich_profile["profile"]["id"])
    content = CVContentOutput(
        summary="x",
        skill_categories=[SkillCategoryOutput(category="ML/DL", skills=["pytorch framework"])],
    )
    issues, sanitized = validate_skill_categories(content, ctx)
    assert issues == []
    assert sanitized[0]["skills"] == ["pytorch framework"]


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
