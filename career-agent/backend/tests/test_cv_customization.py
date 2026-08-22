from unittest.mock import MagicMock

import pytest

from app.ai.client import AIConfigurationError
from app.ai.cv_structured_outputs import (
    CVContentOutput,
    CVPlanOutput,
    ExperienceContentOutput,
    ProjectContentOutput,
    RewrittenBullet,
    SkillCategoryOutput,
)
from app.models.enums import EntityType
from app.services import cv_customization_service as svc
from app.services.job_matching_service import get_relevant_career_data


def _fake_client(*parsed_in_order):
    client = MagicMock()
    completions = []
    for parsed in parsed_in_order:
        message = MagicMock()
        message.parsed = parsed
        choice = MagicMock()
        choice.message = message
        completion = MagicMock()
        completion.choices = [choice]
        completions.append(completion)
    client.chat.completions.parse.side_effect = completions
    return client


def _basic_requirements():
    return [
        dict(requirement_text="PyTorch", category="technical_skill", importance="high", required=True, skill_name="PyTorch"),
        dict(requirement_text="Computer Vision", category="technical_skill", importance="high", required=True, skill_name="Computer Vision"),
    ]


# --- 1: CV planning -----------------------------------------------------


def test_generate_cv_plan_selects_relevant_ids(client, rich_profile, db_session, make_analyzed_job):
    job = make_analyzed_job(requirements=_basic_requirements())
    ctx = get_relevant_career_data(db_session, rich_profile["profile"]["id"])

    plan_output = CVPlanOutput(
        target_role="Machine Learning Engineer",
        priority_skills=["PyTorch"],
        selected_experience_ids=[rich_profile["experience"]["id"], 999999],
        selected_project_ids=[rich_profile["project"]["id"]],
        selected_research_ids=[],
        sections=["summary", "skills", "experience", "projects"],
        reasoning="PyTorch and CV are directly relevant.",
    )
    fake_client = _fake_client(plan_output)

    plan = svc.generate_cv_plan(fake_client, "gpt-4o-mini", job, ctx)

    assert plan.selected_experience_ids == [rich_profile["experience"]["id"]]  # 999999 filtered out
    assert plan.selected_project_ids == [rich_profile["project"]["id"]]
    assert plan.priority_skills == ["PyTorch"]


def test_generate_cv_plan_filters_unverified_priority_skills(client, rich_profile, db_session, make_analyzed_job):
    job = make_analyzed_job(requirements=_basic_requirements())
    ctx = get_relevant_career_data(db_session, rich_profile["profile"]["id"])

    plan_output = CVPlanOutput(
        target_role="Machine Learning Engineer",
        priority_skills=["PyTorch", "AWS"],  # AWS is not in the profile
        selected_experience_ids=[rich_profile["experience"]["id"]],
        selected_project_ids=[],
        selected_research_ids=[],
        sections=["summary", "skills"],
        reasoning="x",
    )
    fake_client = _fake_client(plan_output)

    plan = svc.generate_cv_plan(fake_client, "gpt-4o-mini", job, ctx)
    assert plan.priority_skills == ["PyTorch"]


# --- 2 & 3: relevant skill/project selection (covered above + here) -------


def test_generate_cv_content_produces_skill_categories(client, rich_profile, db_session, make_analyzed_job):
    job = make_analyzed_job(requirements=_basic_requirements())
    ctx = get_relevant_career_data(db_session, rich_profile["profile"]["id"])
    from app.schemas.cv_generation import CVPlan
    plan = CVPlan(
        target_role="Machine Learning Engineer", priority_skills=["PyTorch"],
        selected_experience_ids=[rich_profile["experience"]["id"]],
        selected_project_ids=[rich_profile["project"]["id"]], selected_research_ids=[],
        sections=["summary", "skills", "experience", "projects"], reasoning="x",
    )

    content_output = CVContentOutput(
        summary="Machine Learning Engineer with experience in PyTorch.",
        skill_categories=[SkillCategoryOutput(category="ML/DL", skills=["PyTorch"])],
        experience=[], projects=[],
    )
    fake_client = _fake_client(content_output)

    output, sanitized, issues = svc.generate_cv_content(fake_client, "gpt-4o-mini", job, plan, ctx)
    assert issues == []
    assert sanitized["skills"] == [{"category": "ML/DL", "skills": ["PyTorch"]}]


# --- 4: summary generation --------------------------------------------------


def test_summary_with_unsupported_technology_falls_back(client, rich_profile, db_session, make_analyzed_job):
    job = make_analyzed_job(requirements=[
        dict(requirement_text="AWS", category="technical_skill", importance="medium", required=False, skill_name="AWS"),
    ])
    ctx = get_relevant_career_data(db_session, rich_profile["profile"]["id"])
    from app.schemas.cv_generation import CVPlan
    plan = CVPlan(
        target_role="Machine Learning Engineer", priority_skills=[],
        selected_experience_ids=[], selected_project_ids=[], selected_research_ids=[],
        sections=["summary"], reasoning="x",
    )

    bad_summary = CVContentOutput(
        summary="Machine Learning Engineer experienced in AWS cloud deployment.",
        skill_categories=[], experience=[], projects=[],
    )
    # First call (bad) + retry call (still bad) -- validator should catch both times
    fake_client = _fake_client(bad_summary, bad_summary)

    output, sanitized, issues = svc.generate_cv_content(fake_client, "gpt-4o-mini", job, plan, ctx)
    assert any(i.code == "UNSUPPORTED_TECHNOLOGY_IN_SUMMARY" for i in issues)


# --- 5 & 6: bullet rewriting + source traceability --------------------------


def test_bullet_rewrite_traces_to_real_source(client, rich_profile, db_session, make_analyzed_job):
    job = make_analyzed_job(requirements=_basic_requirements())
    ctx = get_relevant_career_data(db_session, rich_profile["profile"]["id"])
    exp_id = rich_profile["experience"]["id"]
    bullet_id = rich_profile["experience"]["bullets"][0]["id"]

    from app.schemas.cv_generation import CVPlan
    plan = CVPlan(
        target_role="Machine Learning Engineer", priority_skills=["PyTorch"],
        selected_experience_ids=[exp_id], selected_project_ids=[], selected_research_ids=[],
        sections=["summary", "experience"], reasoning="x",
    )
    content_output = CVContentOutput(
        summary="Machine Learning Engineer with PyTorch experience.",
        skill_categories=[],
        experience=[ExperienceContentOutput(
            experience_id=exp_id,
            bullets=[RewrittenBullet(source_bullet_id=bullet_id, rewritten_text="Built PyTorch-based medical image segmentation models.")],
        )],
        projects=[],
    )
    fake_client = _fake_client(content_output)

    output, sanitized, issues = svc.generate_cv_content(fake_client, "gpt-4o-mini", job, plan, ctx)
    assert issues == []
    content = svc.assemble_cv_content(job, plan, output, sanitized, ctx)

    assert len(content.experience) == 1
    bullet = content.experience[0].bullets[0]
    assert bullet.source_type == EntityType.EXPERIENCE_BULLET
    assert bullet.source_id == bullet_id
    assert bullet.verified is True
    assert "PyTorch" in bullet.text


def test_bullet_referencing_nonexistent_source_is_rejected(client, rich_profile, db_session, make_analyzed_job):
    job = make_analyzed_job(requirements=_basic_requirements())
    ctx = get_relevant_career_data(db_session, rich_profile["profile"]["id"])
    exp_id = rich_profile["experience"]["id"]

    from app.schemas.cv_generation import CVPlan
    plan = CVPlan(
        target_role="Machine Learning Engineer", priority_skills=[],
        selected_experience_ids=[exp_id], selected_project_ids=[], selected_research_ids=[],
        sections=["experience"], reasoning="x",
    )
    content_output = CVContentOutput(
        summary="x",
        skill_categories=[],
        experience=[ExperienceContentOutput(
            experience_id=exp_id,
            bullets=[RewrittenBullet(source_bullet_id=999999, rewritten_text="A fabricated bullet with no real source.")],
        )],
        projects=[],
    )
    fake_client = _fake_client(content_output, content_output)  # retry uses same bad output again

    output, sanitized, issues = svc.generate_cv_content(fake_client, "gpt-4o-mini", job, plan, ctx)
    assert any(i.code == "UNSUPPORTED_BULLET_SOURCE" for i in issues)
    assert sanitized["experience"].get(exp_id, []) == []


# --- CV version creation / end-to-end generation ----------------------------


def _plan_and_content_for(rich_profile):
    exp_id = rich_profile["experience"]["id"]
    proj_id = rich_profile["project"]["id"]
    bullet_id = rich_profile["experience"]["bullets"][0]["id"]
    result_id = rich_profile["project"]["results"][0]["id"]

    plan_output = CVPlanOutput(
        target_role="Machine Learning Engineer", priority_skills=["PyTorch"],
        selected_experience_ids=[exp_id], selected_project_ids=[proj_id], selected_research_ids=[],
        sections=["summary", "skills", "experience", "projects", "education"],
        reasoning="Directly relevant.",
    )
    content_output = CVContentOutput(
        summary="Machine Learning Engineer with experience in PyTorch and computer vision.",
        skill_categories=[SkillCategoryOutput(category="ML/DL", skills=["PyTorch"])],
        experience=[ExperienceContentOutput(
            experience_id=exp_id,
            bullets=[RewrittenBullet(source_bullet_id=bullet_id, rewritten_text="Developed PyTorch models for medical image segmentation.")],
        )],
        projects=[ProjectContentOutput(
            project_id=proj_id,
            bullets=[RewrittenBullet(source_bullet_id=result_id, rewritten_text="Improved segmentation accuracy")],
        )],
    )
    return plan_output, content_output


def test_generate_cv_creates_version_with_scores_and_traceability(client, rich_profile, db_session, make_analyzed_job):
    job = make_analyzed_job(requirements=_basic_requirements())
    plan_output, content_output = _plan_and_content_for(rich_profile)
    fake_client = _fake_client(plan_output, content_output)

    import app.services.cv_customization_service as svc_mod
    original = svc_mod.get_ai_client
    svc_mod.get_ai_client = lambda: fake_client
    try:
        cv = svc.generate_cv(db_session, job, compile_pdf_flag=False)
    finally:
        svc_mod.get_ai_client = original

    assert cv.version_number == 1
    assert cv.version_name.endswith("V1")
    assert cv.match_score_before is not None
    assert cv.match_score_after is not None
    assert cv.experience[0]["bullets"][0]["source_type"] == "experience_bullet"
    assert cv.experience[0]["bullets"][0]["verified"] is True


def test_generate_cv_versioning_never_overwrites(client, rich_profile, db_session, make_analyzed_job):
    job = make_analyzed_job(requirements=_basic_requirements())

    import app.services.cv_customization_service as svc_mod
    original = svc_mod.get_ai_client

    plan_output, content_output = _plan_and_content_for(rich_profile)
    svc_mod.get_ai_client = lambda: _fake_client(plan_output, content_output)
    try:
        cv1 = svc.generate_cv(db_session, job, compile_pdf_flag=False)
        plan_output2, content_output2 = _plan_and_content_for(rich_profile)
        svc_mod.get_ai_client = lambda: _fake_client(plan_output2, content_output2)
        cv2 = svc.generate_cv(db_session, job, compile_pdf_flag=False)
    finally:
        svc_mod.get_ai_client = original

    assert cv1.id != cv2.id
    assert cv1.version_number == 1
    assert cv2.version_number == 2


def test_generate_cv_without_analyzed_job_raises(db_session, rich_profile):
    from app.models.job import Job
    job = Job(title="X", company="Y", description="d")
    db_session.add(job)
    db_session.commit()
    with pytest.raises(svc.CVGenerationInputError):
        svc.generate_cv(db_session, job, compile_pdf_flag=False)


def test_generate_cv_without_api_key_raises(db_session, rich_profile, make_analyzed_job):
    job = make_analyzed_job(requirements=_basic_requirements())
    with pytest.raises(AIConfigurationError):
        svc.generate_cv(db_session, job, compile_pdf_flag=False)
