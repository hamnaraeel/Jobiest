"""End-to-end Step 5 tests: real Playwright browser against the local
HTML fixtures in tests/fixtures/ (never a real job site), driven entirely
through the HTTP API exactly as a real client would use it. Proves the
two non-negotiable safety guarantees: DRY_RUN stops submission by
default, and a real click only happens after DRY_RUN is off AND explicit
approval was given."""


def test_analyze_page_detects_fields_and_logs_events(client, rich_profile, make_analyzed_job, fixture_url):
    job = make_analyzed_job()
    app_id = client.post(f"/jobs/{job.id}/apply", json={"application_url": fixture_url("test_application.html")}).json()["id"]
    client.post(f"/applications/{app_id}/start-browser")

    analyze = client.post(f"/applications/{app_id}/analyze-page")
    assert analyze.status_code == 200
    assert analyze.json()["captcha_detected"] is False
    assert analyze.json()["login_required"] is False

    review = client.get(f"/applications/{app_id}/review").json()
    labels = {f["label"] for f in review["fields"]}
    assert "Full Name" in labels
    assert "Email Address" in labels
    assert "Resume/CV" in labels

    events = client.get(f"/applications/{app_id}/events").json()
    kinds = [e["event_type"] for e in events]
    assert "page_loaded" in kinds
    assert "field_detected" in kinds


def test_analyze_page_detects_captcha_and_blocks(client, rich_profile, make_analyzed_job, fixture_url):
    job = make_analyzed_job()
    app_id = client.post(f"/jobs/{job.id}/apply", json={"application_url": fixture_url("test_application_captcha.html")}).json()["id"]
    client.post(f"/applications/{app_id}/start-browser")

    analyze = client.post(f"/applications/{app_id}/analyze-page")
    assert analyze.json()["captcha_detected"] is True

    application = client.get(f"/applications/{app_id}").json()
    assert application["status"] == "blocked"

    # No fields should have been detected/persisted -- analysis stops
    # before form_detector even runs.
    review = client.get(f"/applications/{app_id}/review").json()
    assert review["fields"] == []


def test_analyze_page_detects_login_required_and_pauses(client, rich_profile, make_analyzed_job, fixture_url):
    job = make_analyzed_job()
    app_id = client.post(f"/jobs/{job.id}/apply", json={"application_url": fixture_url("test_application_login.html")}).json()["id"]
    client.post(f"/applications/{app_id}/start-browser")

    analyze = client.post(f"/applications/{app_id}/analyze-page")
    assert analyze.json()["login_required"] is True

    application = client.get(f"/applications/{app_id}").json()
    assert application["status"] == "needs_user_input"

    events = client.get(f"/applications/{app_id}/events").json()
    assert any(e["event_type"] == "user_input_required" for e in events)


def test_fill_autofills_high_confidence_profile_fields_and_leaves_sensitive_ones(client, rich_profile, make_analyzed_job, fixture_url):
    client.put("/profile", json={"phone": "+1 555-0100", "linkedin_url": "https://linkedin.com/in/testuser"})
    job = make_analyzed_job()
    app_id = client.post(f"/jobs/{job.id}/apply", json={"application_url": fixture_url("test_application.html")}).json()["id"]
    client.post(f"/applications/{app_id}/start-browser")
    client.post(f"/applications/{app_id}/analyze-page")

    fill = client.post(f"/applications/{app_id}/fill")
    assert fill.status_code == 200
    body = fill.json()
    filled_labels = {f["label"] for f in body["filled"]}
    assert "Full Name" in filled_labels
    assert "Email Address" in filled_labels

    review = client.get(f"/applications/{app_id}/review").json()
    salary_field = next(f for f in review["fields"] if f["label"] == "Expected Salary")
    assert salary_field["status"] != "filled"
    assert salary_field["user_review_required"] is True
    assert salary_field["confidence"] == 0.0


def test_upload_files_uploads_approved_cv_and_cover_letter(
    client, rich_profile, db_session, make_analyzed_job, make_approved_cv, make_approved_cover_letter, dummy_pdf, fixture_url,
):
    job = make_analyzed_job()
    cv = make_approved_cv(job.id, rich_profile["profile"]["id"])
    cv.pdf_path = dummy_pdf("cv.pdf")
    cl = make_approved_cover_letter(job.id, cv.id, rich_profile["profile"]["id"])
    cl.pdf_path = dummy_pdf("cl.pdf")
    db_session.commit()

    app_id = client.post(f"/jobs/{job.id}/apply", json={
        "application_url": fixture_url("test_application.html"), "cv_version_id": cv.id, "cover_letter_id": cl.id,
    }).json()["id"]
    client.post(f"/applications/{app_id}/start-browser")
    client.post(f"/applications/{app_id}/analyze-page")

    fill = client.post(f"/applications/{app_id}/fill").json()
    uploaded_labels = {f["label"] for f in fill["uploaded"]}
    assert "Resume/CV" in uploaded_labels
    assert "Cover Letter" in uploaded_labels
    for f in fill["uploaded"]:
        assert f["final_value"] in (cv.pdf_path, cl.pdf_path)


def test_review_reports_not_ready_when_required_fields_unresolved(client, rich_profile, make_analyzed_job, fixture_url):
    job = make_analyzed_job()
    app_id = client.post(f"/jobs/{job.id}/apply", json={"application_url": fixture_url("test_application.html")}).json()["id"]
    client.post(f"/applications/{app_id}/start-browser")
    client.post(f"/applications/{app_id}/analyze-page")

    review = client.get(f"/applications/{app_id}/review").json()
    assert review["ready_for_submission"] is False
    assert review["warnings"]


def test_submit_blocked_by_dry_run_by_default(client, rich_profile, db_session, make_analyzed_job, make_approved_cv, dummy_pdf, fixture_url):
    job = make_analyzed_job()
    cv = make_approved_cv(job.id, rich_profile["profile"]["id"])
    cv.pdf_path = dummy_pdf("cv.pdf")
    db_session.commit()

    app_id = client.post(f"/jobs/{job.id}/apply", json={"application_url": fixture_url("test_application.html"), "cv_version_id": cv.id}).json()["id"]
    client.post(f"/applications/{app_id}/start-browser")
    client.post(f"/applications/{app_id}/analyze-page")
    client.post(f"/applications/{app_id}/fill")
    client.post(f"/applications/{app_id}/approve-submission")  # even with explicit approval...

    submit = client.post(f"/applications/{app_id}/submit")
    assert submit.status_code == 200
    body = submit.json()
    assert body["submitted"] is False
    assert body["dry_run"] is True
    assert "DRY_RUN" in body["reason"]

    application = client.get(f"/applications/{app_id}").json()
    assert application["status"] != "submitted"


def test_submit_blocked_without_explicit_approval_even_with_dry_run_off(
    client, rich_profile, db_session, make_analyzed_job, make_approved_cv, dummy_pdf, fixture_url, allow_real_submit,
):
    job = make_analyzed_job()
    cv = make_approved_cv(job.id, rich_profile["profile"]["id"])
    cv.pdf_path = dummy_pdf("cv.pdf")
    db_session.commit()

    app_id = client.post(f"/jobs/{job.id}/apply", json={"application_url": fixture_url("test_application.html"), "cv_version_id": cv.id}).json()["id"]
    client.post(f"/applications/{app_id}/start-browser")
    client.post(f"/applications/{app_id}/analyze-page")
    client.post(f"/applications/{app_id}/fill")
    # deliberately never calling approve-submission

    submit = client.post(f"/applications/{app_id}/submit")
    body = submit.json()
    assert body["submitted"] is False
    assert body["dry_run"] is False
    assert "approval" in body["reason"].lower()


def test_submit_succeeds_after_dry_run_off_and_explicit_approval(
    client, rich_profile, db_session, make_analyzed_job, make_approved_cv, make_approved_cover_letter, dummy_pdf, fixture_url, allow_real_submit,
):
    job = make_analyzed_job()
    cv = make_approved_cv(job.id, rich_profile["profile"]["id"])
    cv.pdf_path = dummy_pdf("cv.pdf")
    cl = make_approved_cover_letter(job.id, cv.id, rich_profile["profile"]["id"])
    cl.pdf_path = dummy_pdf("cl.pdf")
    db_session.commit()

    app_id = client.post(f"/jobs/{job.id}/apply", json={
        "application_url": fixture_url("test_application.html"), "cv_version_id": cv.id, "cover_letter_id": cl.id,
    }).json()["id"]
    client.post(f"/applications/{app_id}/start-browser")
    client.post(f"/applications/{app_id}/analyze-page")
    client.post(f"/applications/{app_id}/fill")

    # /fields/{id}/input is for text-style review answers (salary,
    # relocation, free-text questions) -- file fields are handled by
    # fill()'s own upload step above, using the approved CV/cover letter
    # already attached to this application. Values are picked per field
    # type since the browser's own HTML5 constraint validation (a
    # `type="url"` input rejects non-URL text, a <select> only accepts
    # one of its real <option> labels) would otherwise block the actual
    # form submission below, same as a real browser would.
    field_test_values = {
        "select": "Referral", "url": "https://example.com/test", "phone": "+1 555-0101",
        "checkbox": "no", "textarea": "This role matches my background and interests.",
        "text": "N/A", "radio": "yes",
    }
    review = client.get(f"/applications/{app_id}/review").json()
    for f in review["fields"]:
        if f["user_review_required"] and f["status"] != "filled" and f["field_type"] != "file":
            value = field_test_values.get(f["field_type"], "test value")
            resp = client.post(f"/applications/{app_id}/fields/{f['id']}/input", json={"value": value})
            assert resp.status_code == 200, resp.text
            assert resp.json()["status"] == "filled", (f, resp.json())

    approve = client.post(f"/applications/{app_id}/approve-submission")
    assert approve.json()["submission_approved"] is True

    submit = client.post(f"/applications/{app_id}/submit")
    body = submit.json()
    assert body["submitted"] is True, body
    assert body["dry_run"] is False
    assert body["confirmation_reference"]

    application = client.get(f"/applications/{app_id}").json()
    assert application["status"] == "submitted"
    assert application["confirmation_reference"]

    events = client.get(f"/applications/{app_id}/events").json()
    assert any(e["event_type"] == "submission_completed" for e in events)


def test_submit_reports_failure_when_no_confirmation_detected(
    client, rich_profile, db_session, make_analyzed_job, make_approved_cv, dummy_pdf, fixture_url, allow_real_submit,
):
    job = make_analyzed_job()
    cv = make_approved_cv(job.id, rich_profile["profile"]["id"])
    cv.pdf_path = dummy_pdf("cv.pdf")
    db_session.commit()

    app_id = client.post(f"/jobs/{job.id}/apply", json={
        "application_url": fixture_url("test_application_no_confirmation.html"), "cv_version_id": cv.id,
    }).json()["id"]
    client.post(f"/applications/{app_id}/start-browser")
    client.post(f"/applications/{app_id}/analyze-page")
    client.post(f"/applications/{app_id}/fill")
    client.post(f"/applications/{app_id}/approve-submission")

    submit = client.post(f"/applications/{app_id}/submit")
    body = submit.json()
    assert body["submitted"] is False
    assert "could not confirm" in body["reason"].lower()

    application = client.get(f"/applications/{app_id}").json()
    assert application["status"] == "failed"

    events = client.get(f"/applications/{app_id}/events").json()
    assert any(e["event_type"] == "submission_failed" for e in events)


def test_start_browser_is_idempotent_for_same_application(client, rich_profile, make_analyzed_job, fixture_url):
    job = make_analyzed_job()
    app_id = client.post(f"/jobs/{job.id}/apply", json={"application_url": fixture_url("test_application.html")}).json()["id"]

    first = client.post(f"/applications/{app_id}/start-browser")
    second = client.post(f"/applications/{app_id}/start-browser")
    assert first.status_code == 200
    assert second.status_code == 200


def test_cancel_closes_browser_session_and_marks_abandoned(client, rich_profile, make_analyzed_job, fixture_url):
    from app.browser import browser_manager

    job = make_analyzed_job()
    app_id = client.post(f"/jobs/{job.id}/apply", json={"application_url": fixture_url("test_application.html")}).json()["id"]
    client.post(f"/applications/{app_id}/start-browser")
    assert browser_manager.get_session(app_id) is not None

    cancel = client.post(f"/applications/{app_id}/cancel")
    assert cancel.json()["status"] == "abandoned"
    assert browser_manager.get_session(app_id) is None


def test_analyze_page_without_browser_session_returns_409(client, rich_profile, make_analyzed_job, fixture_url):
    job = make_analyzed_job()
    app_id = client.post(f"/jobs/{job.id}/apply", json={"application_url": fixture_url("test_application.html")}).json()["id"]
    analyze = client.post(f"/applications/{app_id}/analyze-page")
    assert analyze.status_code == 409
