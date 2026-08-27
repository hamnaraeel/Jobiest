from unittest.mock import MagicMock

import pytest

from app.ai.client import AIConfigurationError
from app.ai.cv_structured_outputs import CVContentOutput, CVPlanOutput
from app.models.enums import EntityType
from app.schemas.cv_generation import CVPlan
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


# --- 1: CV planning (framing only -- no content selection) -----------------


def test_generate_cv_plan_returns_target_role_and_priority_skills(client, rich_profile, db_session, make_analyzed_job):
    job = make_analyzed_job(requirements=_basic_requirements())
    ctx = get_relevant_career_data(db_session, rich_profile["profile"]["id"])

    plan_output = CVPlanOutput(
        target_role="Machine Learning Engineer", priority_skills=["PyTorch"], reasoning="PyTorch and CV are directly relevant.",
    )
    fake_client = _fake_client(plan_output)

    plan = svc.generate_cv_plan(fake_client, "gpt-4o-mini", job, ctx)

    assert plan.target_role == "Machine Learning Engineer"
    assert plan.priority_skills == ["PyTorch"]


def test_generate_cv_plan_filters_unverified_priority_skills(client, rich_profile, db_session, make_analyzed_job):
    job = make_analyzed_job(requirements=_basic_requirements())
    ctx = get_relevant_career_data(db_session, rich_profile["profile"]["id"])

    plan_output = CVPlanOutput(
        target_role="Machine Learning Engineer", priority_skills=["PyTorch", "AWS"], reasoning="x",  # AWS is not in the profile
    )
    fake_client = _fake_client(plan_output)

    plan = svc.generate_cv_plan(fake_client, "gpt-4o-mini", job, ctx)
    assert plan.priority_skills == ["PyTorch"]


# --- 2: deterministic skill tailoring (never AI-selected) -------------------
#
# Per the user's standing "MASTER CV" instruction, the Skills section is
# always the candidate's full, verified skill list grouped by each
# skill's own stored category, and per-job tailoring only reorders it
# toward the job's requirements -- it never adds, drops, or asks an LLM
# to pick skills.


def test_master_skill_categories_includes_every_verified_skill(client, rich_profile, db_session):
    ctx = get_relevant_career_data(db_session, rich_profile["profile"]["id"])
    categories = svc._master_skill_categories(ctx)
    assert categories == [{"category": "ML/DL", "skills": ["PyTorch"]}]


def test_reorder_skills_for_job_never_adds_or_removes_skills(client, rich_profile, db_session, make_analyzed_job):
    job = make_analyzed_job(requirements=_basic_requirements())
    ctx = get_relevant_career_data(db_session, rich_profile["profile"]["id"])
    plan = CVPlan(target_role="Machine Learning Engineer", priority_skills=["PyTorch"], reasoning="x")

    master = svc._master_skill_categories(ctx)
    reordered = svc._reorder_skills_for_job(master, job, plan)

    master_skills = {s for cat in master for s in cat["skills"]}
    reordered_skills = {s for cat in reordered for s in cat["skills"]}
    assert reordered_skills == master_skills


# --- 3: summary generation --------------------------------------------------


def test_generate_cv_content_produces_summary(client, rich_profile, db_session, make_analyzed_job):
    job = make_analyzed_job(requirements=_basic_requirements())
    ctx = get_relevant_career_data(db_session, rich_profile["profile"]["id"])
    plan = CVPlan(target_role="Machine Learning Engineer", priority_skills=["PyTorch"], reasoning="x")

    content_output = CVContentOutput(summary="Machine Learning Engineer with experience in PyTorch.")
    fake_client = _fake_client(content_output)

    output, issues = svc.generate_cv_content(fake_client, "gpt-4o-mini", job, plan, ctx)
    assert issues == []
    assert output.summary == "Machine Learning Engineer with experience in PyTorch."


def test_summary_with_unsupported_technology_falls_back(client, rich_profile, db_session, make_analyzed_job):
    job = make_analyzed_job(requirements=[
        dict(requirement_text="AWS", category="technical_skill", importance="medium", required=False, skill_name="AWS"),
    ])
    ctx = get_relevant_career_data(db_session, rich_profile["profile"]["id"])
    plan = CVPlan(target_role="Machine Learning Engineer", priority_skills=[], reasoning="x")

    bad_summary = CVContentOutput(summary="Machine Learning Engineer experienced in AWS cloud deployment.")
    # First call (bad) + retry call (still bad) -- validator should catch both times
    fake_client = _fake_client(bad_summary, bad_summary)

    output, issues = svc.generate_cv_content(fake_client, "gpt-4o-mini", job, plan, ctx)
    assert any(i.code == "UNSUPPORTED_TECHNOLOGY_IN_SUMMARY" for i in issues)


# --- 4: the full profile is always included on the assembled CV, verbatim --


def test_assemble_cv_content_includes_full_profile_verbatim(client, rich_profile, db_session, make_analyzed_job):
    job = make_analyzed_job(requirements=_basic_requirements())
    ctx = get_relevant_career_data(db_session, rich_profile["profile"]["id"])
    bullet_id = rich_profile["experience"]["bullets"][0]["id"]
    original_text = rich_profile["experience"]["bullets"][0]["bullet"]

    plan = CVPlan(target_role="Machine Learning Engineer", priority_skills=["PyTorch"], reasoning="x")
    content_output = CVContentOutput(summary="Machine Learning Engineer with PyTorch experience.")
    skill_categories = svc._reorder_skills_for_job(svc._master_skill_categories(ctx), job, plan)

    content = svc.assemble_cv_content(job, plan, content_output, skill_categories, ctx)

    assert len(content.experience) == len(ctx.experiences)
    assert len(content.projects) == len(ctx.projects)
    # The Skills section is always the candidate's full verified skill list.
    assert content.skills[0].skills == ["PyTorch"]
    bullet = content.experience[0].bullets[0]
    assert bullet.source_type == EntityType.EXPERIENCE_BULLET
    assert bullet.source_id == bullet_id
    assert bullet.verified is True
    # Nothing here ever rewrites wording -- the CV bullet is byte-for-byte the candidate's own text.
    assert bullet.text == original_text


# --- CV version creation / end-to-end generation ----------------------------


def _plan_and_content_for(rich_profile):
    plan_output = CVPlanOutput(target_role="Machine Learning Engineer", priority_skills=["PyTorch"], reasoning="Directly relevant.")
    content_output = CVContentOutput(summary="Machine Learning Engineer with experience in PyTorch and computer vision.")
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
    assert cv.skills == [{"category": "ML/DL", "skills": ["PyTorch"]}]
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
