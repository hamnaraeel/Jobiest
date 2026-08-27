from unittest.mock import MagicMock

from app.ai.cv_structured_outputs import CVContentOutput, CVPlanOutput
from app.models.cv_change import CVChange
from app.models.enums import CVStatus
from app.schemas.cv_generation import CVPlan
from app.services import cv_comparison_service
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


def _plan_and_content(rich_profile):
    plan_output = CVPlanOutput(target_role="Machine Learning Engineer", priority_skills=["PyTorch"], reasoning="Relevant.")
    content_output = CVContentOutput(summary="Machine Learning Engineer with experience in PyTorch.")
    return plan_output, content_output


# --- 13: CV comparison -------------------------------------------------------


def test_build_cv_changes_flags_emphasized_and_deemphasized_skills(client, rich_profile, db_session):
    # add a second, unused skill so it shows up as de-emphasized
    client.post("/skills", json={"profile_id": rich_profile["profile"]["id"], "name": "Excel", "category": "Tool", "verified": True})

    ctx = get_relevant_career_data(db_session, rich_profile["profile"]["id"])
    plan = CVPlan(target_role="Machine Learning Engineer", priority_skills=["PyTorch"], reasoning="x")
    sanitized = {"summary": "New summary text.", "skills": [{"category": "ML/DL", "skills": ["PyTorch"]}]}

    changes = cv_comparison_service.build_cv_changes(plan, sanitized, ctx)
    change_types_by_section = {(c.change_type.value, c.section.value, c.original_text, c.customized_text) for c in changes}

    assert ("emphasized", "skills", None, "pytorch") in change_types_by_section
    assert any(c.change_type.value == "de_emphasized" and c.original_text == "excel" for c in changes)
    assert any(c.change_type.value == "rewritten" and c.section.value == "summary" for c in changes)


def test_comparison_response_aggregates_changes(client, rich_profile, db_session):
    ctx = get_relevant_career_data(db_session, rich_profile["profile"]["id"])
    plan = CVPlan(target_role="Machine Learning Engineer", priority_skills=["PyTorch"], reasoning="x")
    sanitized = {"summary": "New summary text.", "skills": [{"category": "ML/DL", "skills": ["PyTorch"]}]}
    changes = cv_comparison_service.build_cv_changes(plan, sanitized, ctx)

    from app.models.job import Job
    job = Job(title="ML Engineer", company="Acme", description="d")
    db_session.add(job)
    db_session.flush()

    from app.models.cv_version import CVVersion
    cv = CVVersion(
        job_id=job.id, profile_id=rich_profile["profile"]["id"], version_name="Test - V1", version_number=1,
        template_name="ats/ml_engineer", status=CVStatus.DRAFT, match_score_before=70, match_score_after=85,
    )
    db_session.add(cv)
    db_session.flush()
    for c in changes:
        c.cv_version_id = cv.id
        db_session.add(c)
    db_session.commit()

    response = cv_comparison_service.build_comparison_response(cv, changes)
    assert response.match_score_before == 70
    assert response.match_score_after == 85
    assert "pytorch" in response.added_skills
    assert response.summary_changed is True
    assert len(response.changes) == len(changes)


# --- 12: CV version creation (API level) / 18: approval workflow -----------


def test_generate_list_get_and_approve_cv(client, rich_profile, db_session):
    from app.models.job import Job
    from app.models.job_requirement import JobRequirement
    from datetime import datetime, timezone

    job = Job(title="ML Engineer", company="Acme", description="d", extracted_at=datetime.now(timezone.utc))
    db_session.add(job)
    db_session.flush()
    db_session.add(JobRequirement(
        job_id=job.id, requirement_text="PyTorch", category="technical_skill",
        importance="high", required=True, skill_name="PyTorch",
    ))
    db_session.commit()
    job_id = job.id

    plan_output, content_output = _plan_and_content(rich_profile)

    import app.services.cv_customization_service as svc_mod
    original = svc_mod.get_ai_client
    svc_mod.get_ai_client = lambda: _fake_client(plan_output, content_output)
    try:
        resp = client.post(f"/jobs/{job_id}/cv/generate", json={"compile_pdf": False})
    finally:
        svc_mod.get_ai_client = original

    assert resp.status_code == 201
    cv = resp.json()
    cv_id = cv["id"]
    assert cv["version_number"] == 1

    listed = client.get("/cvs").json()
    assert listed["total"] == 1

    fetched = client.get(f"/cvs/{cv_id}").json()
    assert fetched["id"] == cv_id

    # human approval workflow: draft/validated -> approved
    approve_resp = client.patch(f"/cvs/{cv_id}/status", json={"status": "approved"})
    assert approve_resp.status_code == 200
    assert approve_resp.json()["status"] == "approved"

    # DELETE archives rather than hard-deleting
    delete_resp = client.delete(f"/cvs/{cv_id}")
    assert delete_resp.status_code == 200
    assert delete_resp.json()["status"] == "archived"

    still_there = client.get(f"/cvs/{cv_id}")
    assert still_there.status_code == 200
    assert still_there.json()["status"] == "archived"

    # archived is terminal
    blocked = client.patch(f"/cvs/{cv_id}/status", json={"status": "approved"})
    assert blocked.status_code == 409


def test_download_without_pdf_returns_404(client, rich_profile, db_session):
    from app.models.job import Job
    from app.models.job_requirement import JobRequirement
    from datetime import datetime, timezone

    job = Job(title="ML Engineer", company="Acme", description="d", extracted_at=datetime.now(timezone.utc))
    db_session.add(job)
    db_session.flush()
    db_session.add(JobRequirement(
        job_id=job.id, requirement_text="PyTorch", category="technical_skill",
        importance="high", required=True, skill_name="PyTorch",
    ))
    db_session.commit()

    plan_output, content_output = _plan_and_content(rich_profile)
    import app.services.cv_customization_service as svc_mod
    original = svc_mod.get_ai_client
    svc_mod.get_ai_client = lambda: _fake_client(plan_output, content_output)
    try:
        resp = client.post(f"/jobs/{job.id}/cv/generate", json={"compile_pdf": False})
    finally:
        svc_mod.get_ai_client = original

    cv_id = resp.json()["id"]
    download_resp = client.get(f"/cvs/{cv_id}/download")
    assert download_resp.status_code == 404
