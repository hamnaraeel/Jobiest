"""The full Step 1 -> Step 7 workflow, end to end, through the real API
(spec sections 64, 75): Career Profile -> Job discovery/analysis/match ->
Tailored CV -> Cover letter + answers -> Browser-assisted application
(real Playwright, local fixture, real submission with explicit approval)
-> Tracking (status history, interview, follow-up, dashboard) ->
Intelligence (priority/opportunity scoring, recommendations, weekly
review, career strategy).

AI calls (OpenAI for CV/matching-explanation, Ollama for cover letter/
answers/interview prep) are mocked, same as every other test in this
suite -- nothing here depends on a real API key or a running Ollama
instance. Step 5's browser automation is real Playwright against the
local HTML fixture, never a real job site.
"""

from app.ai.cv_structured_outputs import CVContentOutput, CVPlanOutput, ExperienceContentOutput, ProjectContentOutput, RewrittenBullet, SkillCategoryOutput
from app.ai.structured_outputs import ApplicationAnswerOutput, CoverLetterOutput
from app.models.enums import ApplicationStatus, JobStatus


def _fake_openai_client(*parsed_in_order):
    from unittest.mock import MagicMock

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


def test_full_step_1_to_7_workflow(
    client, rich_profile, db_session, make_analyzed_job, mocker, fake_ollama_client, fixture_url, allow_real_submit,
):
    profile = rich_profile["profile"]
    experience = rich_profile["experience"]
    project = rich_profile["project"]

    # --- Step 2: job discovery, analysis, match ----------------------------
    job = make_analyzed_job(
        title="Machine Learning Engineer", company="Example Company",
        requirements=[dict(requirement_text="PyTorch", category="technical_skill", importance="high", required=True, skill_name="PyTorch")],
    )
    job.url = "https://example.com/careers/ml-engineer"
    db_session.commit()

    match_resp = client.post(f"/jobs/{job.id}/match")
    assert match_resp.status_code == 200
    match_score = match_resp.json()["score"]
    assert match_score > 0

    status_resp = client.patch(f"/jobs/{job.id}/status", json={"status": "shortlisted"})
    assert status_resp.json()["status"] == "shortlisted"

    # --- Step 3: tailored CV -------------------------------------------
    plan_output = CVPlanOutput(
        target_role="Machine Learning Engineer", priority_skills=["PyTorch"],
        selected_experience_ids=[experience["id"]], selected_project_ids=[project["id"]], selected_research_ids=[],
        sections=["summary", "skills", "experience", "projects"], reasoning="PyTorch experience is directly relevant.",
    )
    content_output = CVContentOutput(
        summary="Machine Learning Engineer with hands-on PyTorch experience.",
        skill_categories=[SkillCategoryOutput(category="ML/DL", skills=["PyTorch"])],
        experience=[ExperienceContentOutput(experience_id=experience["id"], bullets=[
            RewrittenBullet(source_bullet_id=experience["bullets"][0]["id"], rewritten_text=experience["bullets"][0]["bullet"]),
        ])],
        projects=[ProjectContentOutput(project_id=project["id"], bullets=[])],
    )
    mocker.patch("app.services.cv_customization_service.get_ai_client", return_value=_fake_openai_client(plan_output, content_output))
    cv_resp = client.post(f"/jobs/{job.id}/cv/generate")
    assert cv_resp.status_code == 201, cv_resp.text
    cv_id = cv_resp.json()["id"]
    approve_cv = client.patch(f"/cvs/{cv_id}/status", json={"status": "approved"})
    assert approve_cv.json()["status"] == "approved"

    # --- Step 4: cover letter + application answer -------------------------
    cl_output = CoverLetterOutput(
        opening="x", role_alignment="x", experience_alignment="x", company_alignment="x", closing="x",
        full_text="I'm excited to apply for the Machine Learning Engineer role, where my PyTorch experience directly applies. " * 5,
    )
    mocker.patch("app.services.cover_letter_service.get_ollama_client", return_value=fake_ollama_client(cl_output))
    cl_resp = client.post(f"/jobs/{job.id}/cover-letter/generate")
    assert cl_resp.status_code == 201, cl_resp.text
    cl_id = cl_resp.json()["id"]
    client.patch(f"/cover-letters/{cl_id}/status", json={"status": "approved"})

    question_resp = client.post(f"/jobs/{job.id}/application-questions", json={"question": "Why do you want to work here?", "required": True})
    question_id = question_resp.json()["id"]
    answer_output = ApplicationAnswerOutput(answer="I'm passionate about applying my PyTorch experience to real-world ML systems here.")
    mocker.patch("app.services.application_answer_service.get_ollama_client", return_value=fake_ollama_client(answer_output))
    answer_resp = client.post(f"/jobs/{job.id}/application-questions/{question_id}/answer")
    answer_id = answer_resp.json()["id"]
    client.patch(f"/application-answers/{answer_id}/status", json={"status": "approved"})

    # --- Step 5: browser-assisted application, real submission ----------
    app_resp = client.post(f"/jobs/{job.id}/apply", json={
        "application_url": fixture_url("test_application.html"), "cv_version_id": cv_id, "cover_letter_id": cl_id, "source": "company_website",
    })
    assert app_resp.status_code == 201
    application_id = app_resp.json()["id"]

    client.post(f"/applications/{application_id}/start-browser")
    client.post(f"/applications/{application_id}/analyze-page")
    client.post(f"/applications/{application_id}/fill")

    review = client.get(f"/applications/{application_id}/review").json()
    for f in review["fields"]:
        if f["user_review_required"] and f["status"] != "filled" and f["field_type"] != "file":
            value = {"select": "Referral", "url": "https://example.com/portfolio", "checkbox": "no"}.get(f["field_type"], "N/A")
            client.post(f"/applications/{application_id}/fields/{f['id']}/input", json={"value": value})

    client.post(f"/applications/{application_id}/approve-submission")
    submit_resp = client.post(f"/applications/{application_id}/submit")
    assert submit_resp.json()["submitted"] is True, submit_resp.json()
    # Browser session cleanup is handled by the autouse fixture in
    # conftest.py at test teardown -- calling /cancel here would
    # overwrite the just-confirmed "submitted" status with "abandoned"
    # (cancel() unconditionally sets ABANDONED, regardless of the
    # application's current status), which is the wrong tool for merely
    # closing a browser session after a successful submission.

    application = client.get(f"/applications/{application_id}").json()
    assert application["status"] == "submitted"
    assert application["material_snapshot"] is not None
    assert application["material_snapshot"]["match_score"] == match_score

    # --- Step 6: tracking ------------------------------------------------
    recruiter_contact = client.patch(f"/applications/{application_id}/status", json={"status": "under_review", "reason": "Recruiter email received."})
    assert recruiter_contact.json()["status"] == "under_review"

    interview_resp = client.post(f"/applications/{application_id}/interviews", json={"type": "technical", "interviewer": "Hiring Manager"})
    assert interview_resp.status_code == 201

    interview_status = client.patch(f"/applications/{application_id}/status", json={"status": "interview", "reason": "Technical interview scheduled."})
    assert interview_status.json()["status"] == "interview"

    followup_resp = client.post(f"/applications/{application_id}/followups", json={
        "due_date": "2026-08-22", "type": "interview_followup", "subject": "Thank interviewer",
    })
    assert followup_resp.status_code == 201
    assert followup_resp.json()["status"] == "pending"

    timeline = client.get(f"/applications/{application_id}/timeline").json()
    entry_types = [e["entry_type"] for e in timeline["entries"]]
    assert "job" in entry_types
    assert "status_change" in entry_types
    assert "interview" in entry_types
    timestamps = [e["timestamp"] for e in timeline["entries"]]
    assert timestamps == sorted(timestamps)

    status_history = client.get(f"/applications/{application_id}/status-history").json()
    new_statuses = [h["new_status"] for h in status_history]
    assert new_statuses == ["submitted", "under_review", "interview"]  # full chain, nothing overwritten

    dashboard = client.get("/dashboard").json()
    assert dashboard["applications"]["submitted"] >= 1
    assert dashboard["interviews"]["total"] >= 1

    readiness = client.get(f"/applications/{application_id}/readiness").json()
    assert readiness["checks"]["cv_approved"] is True
    assert readiness["checks"]["cover_letter_approved"] is True

    # --- Final summary, matching the shape of spec section 75's example ---
    final_job = client.get(f"/jobs/{job.id}").json()
    final_application = client.get(f"/applications/{application_id}").json()
    final_cv = client.get(f"/cvs/{cv_id}").json()
    final_cl = client.get(f"/cover-letters/{cl_id}").json()

    assert final_job["company"] == "Example Company"
    assert final_job["title"] == "Machine Learning Engineer"
    assert final_job["status"] == JobStatus.SHORTLISTED.value
    assert final_application["status"] == ApplicationStatus.INTERVIEW.value
    assert final_cv["status"] == "approved"
    assert final_cl["status"] == "approved"
    assert followup_resp.json()["due_date"] == "2026-08-22"

    # --- Step 7: intelligence ---------------------------------------------
    job_intel = client.get(f"/intelligence/jobs/{job.id}").json()
    assert job_intel["priority"]["score"] >= 0
    assert job_intel["opportunity"]["score"] >= 0
    assert job_intel["priority"]["reasons"]
    assert job_intel["priority"]["confidence_reason"]

    app_intel = client.get(f"/intelligence/applications/{application_id}").json()
    assert app_intel["quality"]["cv_approved"] is True
    assert app_intel["quality"]["cover_letter_approved"] is True
    assert app_intel["interview_preparation"]["company"] == "Example Company"

    generate_resp = client.post("/intelligence/recommendations/generate")
    assert generate_resp.status_code == 200
    recs = generate_resp.json()["items"]
    assert recs
    for rec in recs:
        assert rec["evidence"]
        assert rec["confidence_reason"]
        assert 0.0 <= rec["confidence"] <= 1.0

    top_rec = recs[0]
    accept_resp = client.post(f"/intelligence/recommendations/{top_rec['id']}/accept")
    assert accept_resp.json()["status"] == "accepted"

    weekly_review = client.get("/intelligence/weekly-review").json()
    assert "recommendations" in weekly_review and weekly_review["recommendations"]
    assert "evidence" in weekly_review

    strategy = client.get("/intelligence/strategy").json()
    assert "suggested_weekly_targets" in strategy

    skill_gaps = client.get("/intelligence/skills/gaps").json()["gaps"]
    top_gap = skill_gaps[0] if skill_gaps else None

    cv_perf = client.get("/analytics/cv-versions").json()["cv_versions"]
    best_cv = max(cv_perf, key=lambda label: cv_perf[label]["interviews"]) if cv_perf else None

    source_perf = client.get("/intelligence/career").json()["recommended_sources"]

    # --- Final summary, matching the shape of spec section 64's example ---
    print("========================================")
    print("AI JOB SEARCH INTELLIGENCE")
    print("==========================")
    print(f"Top Recommendation: {top_rec['title']}")
    print(f"Confidence: {top_rec['confidence']}")
    if top_gap:
        print(f"Top Skill Gap: {top_gap['skill']} (priority: {top_gap['priority']})")
    print(f"Best Observed CV: {best_cv}")
    print(f"Best Source: {source_perf}")
    print(f"Next Week: {weekly_review['recommendations'][0]}")
    print("========================================")

    assert top_rec["title"]
    assert best_cv is not None
