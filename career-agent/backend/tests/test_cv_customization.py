from unittest.mock import MagicMock

import pytest

from app.ai.client import AIConfigurationError
from app.ai.cv_structured_outputs import (
    CVBulletRewriteOutput,
    CVContentOutput,
    CVPlanOutput,
    RewrittenBullet,
)
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


# --- AI bullet rewriting ----------------------------------------------------
#
# Rewriting is allowed to change the candidate's wording to match the job
# description, but never their facts. Every test below is really one
# question: when the model does something other than a faithful reword,
# does the CV still ship the candidate's own text?

_ORIGINAL_BULLET = "Developed deep learning models for medical image segmentation using PyTorch."


def _assembled_content(db_session, rich_profile, job):
    ctx = get_relevant_career_data(db_session, rich_profile["profile"]["id"])
    plan = CVPlan(target_role="Machine Learning Engineer", priority_skills=["PyTorch"], reasoning="x")
    content_output = CVContentOutput(summary="Machine Learning Engineer with PyTorch experience.")
    skill_categories = svc._reorder_skills_for_job(svc._master_skill_categories(ctx), job, plan)
    return svc.assemble_cv_content(job, plan, content_output, skill_categories, ctx), plan, ctx


def _rewrite(db_session, rich_profile, job, rewrites, client_factory=None):
    content, plan, ctx = _assembled_content(db_session, rich_profile, job)
    assert content.experience[0].bullets[0].text == _ORIGINAL_BULLET
    fake = client_factory() if client_factory else _fake_client(
        CVBulletRewriteOutput(bullets=[RewrittenBullet(id=i, text=t) for i, t in rewrites])
    )
    return svc.rewrite_bullets_for_job(fake, "gpt-4o-mini", job, plan, content, ctx)


def test_rewrite_bullets_applies_a_faithful_reword(client, rich_profile, db_session, make_analyzed_job):
    job = make_analyzed_job(requirements=_basic_requirements())
    reworded = "Built deep learning models for medical image segmentation in PyTorch"

    content, applied = _rewrite(db_session, rich_profile, job, [("e0b0", reworded)])

    assert content.experience[0].bullets[0].text == reworded
    assert [(o, r) for o, r, _ in applied] == [(_ORIGINAL_BULLET, reworded)]


def test_rewrite_bullets_reverts_an_invented_metric(client, rich_profile, db_session, make_analyzed_job):
    job = make_analyzed_job(requirements=_basic_requirements())
    invented = "Built deep learning models for medical image segmentation in PyTorch, improving accuracy by 35%"

    content, applied = _rewrite(db_session, rich_profile, job, [("e0b0", invented)])

    assert content.experience[0].bullets[0].text == _ORIGINAL_BULLET
    assert applied == []


def test_rewrite_bullets_reverts_an_invented_technology(client, rich_profile, db_session, make_analyzed_job):
    job = make_analyzed_job(requirements=_basic_requirements())
    # "Computer Vision" is a requirement of this job and a skill on the
    # profile -- being real elsewhere does not make it true of a bullet
    # that never mentioned it.
    invented = "Built deep learning computer vision models for medical image segmentation in PyTorch"

    content, applied = _rewrite(db_session, rich_profile, job, [("e0b0", invented)])

    assert content.experience[0].bullets[0].text == _ORIGINAL_BULLET
    assert applied == []


def test_rewrite_bullets_ignores_ids_it_was_never_given(client, rich_profile, db_session, make_analyzed_job):
    job = make_analyzed_job(requirements=_basic_requirements())

    content, applied = _rewrite(db_session, rich_profile, job, [("e7b7", "Led a team of 40 engineers")])

    assert content.experience[0].bullets[0].text == _ORIGINAL_BULLET
    assert applied == []


def test_rewrite_bullets_keeps_originals_when_the_model_omits_them(client, rich_profile, db_session, make_analyzed_job):
    job = make_analyzed_job(requirements=_basic_requirements())

    content, applied = _rewrite(db_session, rich_profile, job, [])

    assert content.experience[0].bullets[0].text == _ORIGINAL_BULLET
    assert content.projects[0].bullets[0].text
    assert applied == []


def test_rewrite_bullets_survives_an_unavailable_model(client, rich_profile, db_session, make_analyzed_job):
    """An LLM failure degrades to the verbatim CV -- it is never a
    generation error, because the stored bullet is always a correct
    answer."""

    job = make_analyzed_job(requirements=_basic_requirements())

    def exploding_client():
        failing = MagicMock()
        failing.chat.completions.parse.side_effect = RuntimeError("upstream is down")
        return failing

    content, applied = _rewrite(db_session, rich_profile, job, [], client_factory=exploding_client)

    assert content.experience[0].bullets[0].text == _ORIGINAL_BULLET
    assert applied == []


def test_generate_cv_records_applied_rewrites_in_the_audit_trail(client, rich_profile, db_session, make_analyzed_job):
    from app.models.cv_change import CVChange
    from app.models.enums import CVChangeType, CVSectionType

    job = make_analyzed_job(requirements=_basic_requirements())
    reworded = "Built deep learning models for medical image segmentation in PyTorch"
    plan_output, content_output, rewrite_output = _plan_and_content_for(rich_profile, [("e0b0", reworded)])

    import app.services.cv_customization_service as svc_mod
    original = svc_mod.get_ai_client
    svc_mod.get_ai_client = lambda: _fake_client(plan_output, content_output, rewrite_output)
    try:
        cv = svc.generate_cv(db_session, job, compile_pdf_flag=False)
    finally:
        svc_mod.get_ai_client = original

    assert cv.experience[0]["bullets"][0]["text"] == reworded
    changes = db_session.query(CVChange).filter(
        CVChange.cv_version_id == cv.id, CVChange.section == CVSectionType.EXPERIENCE
    ).all()
    assert [(c.change_type, c.original_text, c.customized_text) for c in changes] == [
        (CVChangeType.REWRITTEN, _ORIGINAL_BULLET, reworded)
    ]


# --- CV version creation / end-to-end generation ----------------------------


def _plan_and_content_for(rich_profile, rewrites=()):
    """The three structured outputs generate_cv() consumes, in order:
    plan, summary, bullet rewrites. `rewrites` defaults to empty, which
    leaves every bullet at the candidate's stored text."""

    plan_output = CVPlanOutput(target_role="Machine Learning Engineer", priority_skills=["PyTorch"], reasoning="Directly relevant.")
    content_output = CVContentOutput(summary="Machine Learning Engineer with experience in PyTorch and computer vision.")
    rewrite_output = CVBulletRewriteOutput(bullets=[RewrittenBullet(id=i, text=t) for i, t in rewrites])
    return plan_output, content_output, rewrite_output


def test_generate_cv_creates_version_with_scores_and_traceability(client, rich_profile, db_session, make_analyzed_job):
    job = make_analyzed_job(requirements=_basic_requirements())
    plan_output, content_output, rewrite_output = _plan_and_content_for(rich_profile)
    fake_client = _fake_client(plan_output, content_output, rewrite_output)

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

    plan_output, content_output, rewrite_output = _plan_and_content_for(rich_profile)
    svc_mod.get_ai_client = lambda: _fake_client(plan_output, content_output, rewrite_output)
    try:
        cv1 = svc.generate_cv(db_session, job, compile_pdf_flag=False)
        plan_output2, content_output2, rewrite_output2 = _plan_and_content_for(rich_profile)
        svc_mod.get_ai_client = lambda: _fake_client(plan_output2, content_output2, rewrite_output2)
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
