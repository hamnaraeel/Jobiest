from app.ai.cv_structured_outputs import CVContentOutput, ExperienceContentOutput, RewrittenBullet, SkillCategoryOutput
from app.services.cv_validation_service import validate_bullets, validate_skill_categories, validate_summary
from app.services.job_matching_service import get_relevant_career_data


# --- 7: unsupported skill detection -----------------------------------------


def test_unsupported_skill_detected_and_stripped(client, rich_profile, db_session):
    ctx = get_relevant_career_data(db_session, rich_profile["profile"]["id"])
    content = CVContentOutput(
        summary="x",
        skill_categories=[SkillCategoryOutput(category="Cloud", skills=["PyTorch", "AWS"])],
        experience=[], projects=[],
    )
    issues, sanitized = validate_skill_categories(content, ctx)

    assert any(i.code == "UNSUPPORTED_SKILL" and "AWS" in i.message for i in issues)
    assert sanitized == [{"category": "Cloud", "skills": ["PyTorch"]}]


def test_verified_skill_passes_validation(client, rich_profile, db_session):
    ctx = get_relevant_career_data(db_session, rich_profile["profile"]["id"])
    content = CVContentOutput(
        summary="x",
        skill_categories=[SkillCategoryOutput(category="ML/DL", skills=["PyTorch"])],
        experience=[], projects=[],
    )
    issues, sanitized = validate_skill_categories(content, ctx)
    assert issues == []
    assert sanitized == [{"category": "ML/DL", "skills": ["PyTorch"]}]


def test_skill_name_variant_recognized_via_normalization(client, rich_profile, db_session):
    ctx = get_relevant_career_data(db_session, rich_profile["profile"]["id"])
    content = CVContentOutput(
        summary="x",
        skill_categories=[SkillCategoryOutput(category="ML/DL", skills=["pytorch framework"])],
        experience=[], projects=[],
    )
    issues, sanitized = validate_skill_categories(content, ctx)
    assert issues == []
    assert sanitized[0]["skills"] == ["pytorch framework"]


# --- 8: unsupported technology detection ------------------------------------


def test_unsupported_technology_in_bullet_reverts_to_original(client, rich_profile, db_session):
    ctx = get_relevant_career_data(db_session, rich_profile["profile"]["id"])
    bullet_id = rich_profile["experience"]["bullets"][0]["id"]
    original_text = rich_profile["experience"]["bullets"][0]["bullet"]

    bullets = [RewrittenBullet(source_bullet_id=bullet_id, rewritten_text="Deployed models using AWS for segmentation.")]
    issues, sanitized = validate_bullets(
        bullets, {bullet_id}, {bullet_id: original_text}, {bullet_id: {"pytorch"}}, ctx, "experience",
        watch_terms=["AWS"],
    )

    assert any(i.code == "UNSUPPORTED_TECHNOLOGY" for i in issues)
    assert sanitized[0]["text"] == original_text


def test_supported_technology_rewrite_is_kept(client, rich_profile, db_session):
    ctx = get_relevant_career_data(db_session, rich_profile["profile"]["id"])
    bullet_id = rich_profile["experience"]["bullets"][0]["id"]
    original_text = rich_profile["experience"]["bullets"][0]["bullet"]

    bullets = [RewrittenBullet(source_bullet_id=bullet_id, rewritten_text="Built PyTorch models for segmentation.")]
    issues, sanitized = validate_bullets(
        bullets, {bullet_id}, {bullet_id: original_text}, {bullet_id: {"pytorch"}}, ctx, "experience",
    )

    assert issues == []
    assert sanitized[0]["text"] == "Built PyTorch models for segmentation."


# --- 9: unsupported metric detection ----------------------------------------


def test_unsupported_metric_in_bullet_reverts_to_original(client, rich_profile, db_session):
    ctx = get_relevant_career_data(db_session, rich_profile["profile"]["id"])
    bullet_id = rich_profile["experience"]["bullets"][0]["id"]
    original_text = rich_profile["experience"]["bullets"][0]["bullet"]

    bullets = [RewrittenBullet(source_bullet_id=bullet_id, rewritten_text=original_text + " Improved accuracy by 30%.")]
    issues, sanitized = validate_bullets(
        bullets, {bullet_id}, {bullet_id: original_text}, {bullet_id: set()}, ctx, "experience",
    )

    assert any(i.code == "UNSUPPORTED_METRIC" for i in issues)
    assert sanitized[0]["text"] == original_text


def test_metric_already_present_in_original_is_allowed(client, rich_profile, db_session):
    ctx = get_relevant_career_data(db_session, rich_profile["profile"]["id"])
    bullet_id = rich_profile["experience"]["bullets"][0]["id"]
    original_text = "Improved segmentation accuracy by 6.2%."

    bullets = [RewrittenBullet(source_bullet_id=bullet_id, rewritten_text="Achieved a 6.2% improvement in segmentation accuracy.")]
    issues, sanitized = validate_bullets(
        bullets, {bullet_id}, {bullet_id: original_text}, {bullet_id: set()}, ctx, "experience",
    )

    assert issues == []


# --- 10: unsupported project/bullet-source detection ------------------------


def test_bullet_with_unknown_source_id_is_rejected(client, rich_profile, db_session):
    ctx = get_relevant_career_data(db_session, rich_profile["profile"]["id"])
    bullets = [RewrittenBullet(source_bullet_id=99999, rewritten_text="Fabricated bullet.")]
    issues, sanitized = validate_bullets(
        bullets, {1, 2, 3}, {1: "a", 2: "b", 3: "c"}, {}, ctx, "experience",
    )
    assert any(i.code == "UNSUPPORTED_BULLET_SOURCE" for i in issues)
    assert sanitized == []


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
