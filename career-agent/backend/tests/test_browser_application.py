"""Unit-level Step 5 tests that don't need a real browser -- field
mapping, the submission safety gate, platform detection, and the
DB-orchestration layer's own rules (duplicate detection, approval,
pause/resume, user input). See test_browser_application_e2e.py for the
real-Playwright-against-local-fixture tests (CAPTCHA/login detection,
autofill, upload, submit)."""

import pytest

from app.browser import field_mapper, submission_guard
from app.browser.form_detector import DetectedField
from app.browser.platform_detector import detect_platform, get_adapter
from app.models.application_answer import ApplicationAnswer
from app.models.application_question import ApplicationQuestion
from app.models.enums import ApplicationFieldStatus, ApplicationFieldType, ApplicationMaterialStatus
from app.services import application_service


def _field(**overrides):
    defaults = dict(field_identifier="f", label="Full Name", field_type=ApplicationFieldType.TEXT, required=False)
    defaults.update(overrides)
    return DetectedField(**defaults)


def _profile_obj(rich_profile):
    from app.models.profile import CareerProfile

    return CareerProfile(**{k: v for k, v in rich_profile["profile"].items() if k in CareerProfile.__table__.columns.keys()})


def _question_answer(db_session, job_id, question_text, answer_text, status=ApplicationMaterialStatus.APPROVED):
    question = ApplicationQuestion(job_id=job_id, question=question_text)
    db_session.add(question)
    db_session.flush()
    answer = ApplicationAnswer(question_id=question.id, answer=answer_text, word_count=len(answer_text.split()), character_count=len(answer_text), status=status)
    db_session.add(answer)
    db_session.commit()
    db_session.refresh(question)
    db_session.refresh(answer)
    return question, answer


# --- field_mapper: profile field mapping ------------------------------------


def test_field_mapper_maps_full_name_from_profile(client, rich_profile):
    profile = _profile_obj(rich_profile)
    mapping = field_mapper.map_field(_field(label="Full Name"), profile, [])
    assert mapping.mapped_source == "profile.full_name"
    assert mapping.confidence == field_mapper.PROFILE_MATCH_CONFIDENCE
    assert mapping.proposed_value == profile.full_name


def test_field_mapper_declines_when_profile_field_empty(client, rich_profile):
    profile = _profile_obj(rich_profile)
    profile.github_url = None
    mapping = field_mapper.map_field(_field(label="GitHub URL"), profile, [])
    assert mapping.mapped_source is None
    assert mapping.confidence == 0.0


def test_field_mapper_declines_without_profile():
    mapping = field_mapper.map_field(_field(label="Full Name"), None, [])
    assert mapping.mapped_source is None
    assert mapping.confidence == 0.0


# --- field_mapper: sensitive questions never auto-answered -------------------


@pytest.mark.parametrize("label", [
    "Expected Salary", "Are you authorized to work in this country?",
    "Are you willing to relocate?", "When are you available to start?",
    "Do you require visa sponsorship?", "What is your notice period?",
])
def test_field_mapper_never_maps_sensitive_fields(label):
    assert field_mapper.is_sensitive_label(label) is True
    mapping = field_mapper.map_field(_field(label=label, field_type=ApplicationFieldType.TEXT), None, [])
    assert mapping.confidence == 0.0
    assert mapping.mapped_source is None


def test_field_mapper_file_field_always_declines():
    mapping = field_mapper.map_field(_field(label="Resume", field_type=ApplicationFieldType.FILE), None, [])
    assert mapping.mapped_source is None
    assert mapping.confidence == 0.0


# --- field_mapper: matching Step 4 application answers ------------------------


def test_field_mapper_matches_approved_answer_high_confidence(db_session, make_analyzed_job, rich_profile):
    job = make_analyzed_job()
    question, answer = _question_answer(db_session, job.id, "Why do you want to work here?", "Because I love building things.")
    mapping = field_mapper.map_field(
        _field(label="Why do you want to work here?", field_type=ApplicationFieldType.TEXTAREA), _profile_obj(rich_profile), [(question, answer)],
    )
    assert mapping.mapped_source == f"application_answer_{answer.id}"
    assert mapping.confidence == field_mapper.HIGH_TEXT_MATCH_CONFIDENCE


def test_field_mapper_matches_unapproved_answer_at_lower_confidence(db_session, make_analyzed_job, rich_profile):
    job = make_analyzed_job()
    question, answer = _question_answer(
        db_session, job.id, "Why do you want to work here?", "Because I love building things.", status=ApplicationMaterialStatus.DRAFT,
    )
    mapping = field_mapper.map_field(
        _field(label="Why do you want to work here?", field_type=ApplicationFieldType.TEXTAREA), _profile_obj(rich_profile), [(question, answer)],
    )
    assert mapping.mapped_source == f"application_answer_{answer.id}"
    assert mapping.confidence == field_mapper.UNAPPROVED_MATCH_CONFIDENCE
    assert mapping.confidence < field_mapper.HIGH_TEXT_MATCH_CONFIDENCE


def test_field_mapper_no_answer_match_declines(db_session, make_analyzed_job, rich_profile):
    job = make_analyzed_job()
    question, answer = _question_answer(db_session, job.id, "Describe your leadership experience.", "I led a team of five.")
    mapping = field_mapper.map_field(
        _field(label="What is your favorite color?", field_type=ApplicationFieldType.TEXTAREA), _profile_obj(rich_profile), [(question, answer)],
    )
    assert mapping.mapped_source is None


# --- submission_guard --------------------------------------------------------


def _application(**overrides):
    from app.models.application import Application
    from app.models.enums import ApplicationStatus

    defaults = dict(job_id=1, submission_approved=False, status=ApplicationStatus.READY_FOR_REVIEW)
    defaults.update(overrides)
    return Application(**defaults)


def test_submission_guard_blocks_on_unresolved_required_field(make_approved_cv, db_session, make_analyzed_job, rich_profile):
    job = make_analyzed_job()
    cv = make_approved_cv(job.id, rich_profile["profile"]["id"])
    field_row = None
    from app.models.application_field import ApplicationField

    field_row = ApplicationField(
        application_id=1, field_identifier="f", label="Full Name", field_type=ApplicationFieldType.TEXT,
        required=True, status=ApplicationFieldStatus.DETECTED,
    )
    application = _application(cv_version_id=cv.id, submission_approved=True)
    check = submission_guard.check_ready_for_submission(application, [field_row], cv, None)
    assert check.ready is False
    assert any("required field" in w for w in check.warnings)


def test_submission_guard_blocks_when_cv_not_approved(db_session, make_analyzed_job, rich_profile):
    from app.models.cv_version import CVVersion
    from app.models.enums import CVStatus

    job = make_analyzed_job()
    cv = CVVersion(job_id=job.id, profile_id=rich_profile["profile"]["id"], version_name="v1", version_number=1, template_name="ats/ml_engineer", status=CVStatus.DRAFT)
    db_session.add(cv)
    db_session.commit()
    db_session.refresh(cv)

    application = _application(cv_version_id=cv.id, submission_approved=True)
    check = submission_guard.check_ready_for_submission(application, [], cv, None)
    assert check.ready is False
    assert any("not approved" in w for w in check.warnings)


def test_submission_guard_blocks_without_explicit_approval(make_approved_cv, db_session, make_analyzed_job, rich_profile):
    job = make_analyzed_job()
    cv = make_approved_cv(job.id, rich_profile["profile"]["id"])
    application = _application(cv_version_id=cv.id, submission_approved=False)
    check = submission_guard.check_ready_for_submission(application, [], cv, None)
    assert check.ready is False
    assert any("approval" in w for w in check.warnings)


def test_submission_guard_ready_when_everything_satisfied(make_approved_cv, db_session, make_analyzed_job, rich_profile):
    job = make_analyzed_job()
    cv = make_approved_cv(job.id, rich_profile["profile"]["id"])
    application = _application(cv_version_id=cv.id, submission_approved=True)
    check = submission_guard.check_ready_for_submission(application, [], cv, None)
    assert check.ready is True
    assert check.warnings == []


def test_can_click_submit_blocked_by_dry_run_even_when_ready(make_approved_cv, db_session, make_analyzed_job, rich_profile):
    job = make_analyzed_job()
    cv = make_approved_cv(job.id, rich_profile["profile"]["id"])
    application = _application(cv_version_id=cv.id, submission_approved=True)
    check = submission_guard.check_ready_for_submission(application, [], cv, None)
    allowed, reason = submission_guard.can_click_submit(check, application, dry_run=True)
    assert allowed is False
    assert "DRY_RUN" in reason


def test_can_click_submit_blocked_without_approval_even_with_dry_run_off(make_approved_cv, db_session, make_analyzed_job, rich_profile):
    job = make_analyzed_job()
    cv = make_approved_cv(job.id, rich_profile["profile"]["id"])
    application = _application(cv_version_id=cv.id, submission_approved=False)
    check = submission_guard.check_ready_for_submission(application, [], cv, None)
    allowed, reason = submission_guard.can_click_submit(check, application, dry_run=False)
    assert allowed is False
    assert "approval" in reason.lower()


def test_can_click_submit_allowed_when_dry_run_off_and_approved_and_ready(make_approved_cv, db_session, make_analyzed_job, rich_profile):
    job = make_analyzed_job()
    cv = make_approved_cv(job.id, rich_profile["profile"]["id"])
    application = _application(cv_version_id=cv.id, submission_approved=True)
    check = submission_guard.check_ready_for_submission(application, [], cv, None)
    allowed, reason = submission_guard.can_click_submit(check, application, dry_run=False)
    assert allowed is True
    assert reason == ""


# --- file_uploader: never uploads unapproved materials ------------------------


def test_resolve_cv_pdf_path_rejects_unapproved(db_session, make_analyzed_job, rich_profile):
    from app.browser import file_uploader
    from app.models.cv_version import CVVersion
    from app.models.enums import CVStatus

    job = make_analyzed_job()
    cv = CVVersion(job_id=job.id, profile_id=rich_profile["profile"]["id"], version_name="v1", version_number=1, template_name="ats/ml_engineer", status=CVStatus.DRAFT)
    db_session.add(cv)
    db_session.commit()
    db_session.refresh(cv)

    with pytest.raises(file_uploader.UnapprovedMaterialError):
        file_uploader.resolve_cv_pdf_path(db_session, cv)


def test_resolve_cover_letter_pdf_path_rejects_unapproved(db_session, make_analyzed_job, rich_profile, make_approved_cv):
    from app.browser import file_uploader
    from app.models.cover_letter import CoverLetter
    from app.models.enums import ApplicationMaterialStatus as Status

    job = make_analyzed_job()
    cv = make_approved_cv(job.id, rich_profile["profile"]["id"])
    cl = CoverLetter(
        job_id=job.id, cv_version_id=cv.id, profile_id=rich_profile["profile"]["id"],
        version_name="v1", version_number=1, title="t", content="c", word_count=1, status=Status.DRAFT,
    )
    db_session.add(cl)
    db_session.commit()
    db_session.refresh(cl)

    with pytest.raises(file_uploader.UnapprovedMaterialError):
        file_uploader.resolve_cover_letter_pdf_path(db_session, cl)


def test_resolve_cv_pdf_path_returns_existing_path_for_approved_cv(db_session, make_analyzed_job, rich_profile, make_approved_cv, dummy_pdf):
    from app.browser import file_uploader

    job = make_analyzed_job()
    cv = make_approved_cv(job.id, rich_profile["profile"]["id"])
    cv.pdf_path = dummy_pdf("cv.pdf")
    db_session.commit()

    path = file_uploader.resolve_cv_pdf_path(db_session, cv)
    assert path == cv.pdf_path


def test_resolve_cover_letter_pdf_path_returns_existing_path_for_approved(db_session, make_analyzed_job, rich_profile, make_approved_cv, make_approved_cover_letter, dummy_pdf):
    from app.browser import file_uploader

    job = make_analyzed_job()
    cv = make_approved_cv(job.id, rich_profile["profile"]["id"])
    cl = make_approved_cover_letter(job.id, cv.id, rich_profile["profile"]["id"])
    cl.pdf_path = dummy_pdf("cl.pdf")
    db_session.commit()

    path = file_uploader.resolve_cover_letter_pdf_path(db_session, cl)
    assert path == cl.pdf_path


# --- platform_detector --------------------------------------------------------


@pytest.mark.parametrize("url,expected", [
    ("https://boards.greenhouse.io/acme/jobs/123", "greenhouse"),
    ("https://jobs.lever.co/acme/123", "lever"),
    ("https://acme.wd5.myworkdayjobs.com/careers/job/123", "workday"),
    ("https://www.linkedin.com/jobs/view/123", "linkedin"),
    ("https://www.indeed.com/viewjob?jk=123", "indeed"),
    ("https://careers.acme.com/apply/123", "company_site"),
    (None, "unknown"),
])
def test_detect_platform(url, expected):
    assert detect_platform(url).value == expected


def test_get_adapter_falls_back_to_generic_for_unregistered_platform():
    from app.models.enums import ApplicationPlatform

    adapter = get_adapter(ApplicationPlatform.GREENHOUSE)
    assert adapter.platform_name == "generic"


# --- application_service: creation, duplicate detection ----------------------


def test_create_application_defaults_to_job_url_and_latest_approved_materials(db_session, make_analyzed_job, rich_profile, make_approved_cv):
    job = make_analyzed_job()
    job.url = "https://careers.acme.com/apply/1"
    db_session.commit()
    cv = make_approved_cv(job.id, rich_profile["profile"]["id"])

    application = application_service.create_application(db_session, job)
    assert application.application_url == job.url
    assert application.cv_version_id == cv.id
    assert application.status.value == "not_started"
    assert application.submission_approved is False


def test_create_application_requires_url_when_job_has_none(db_session, make_analyzed_job):
    job = make_analyzed_job()
    job.url = None
    db_session.commit()
    with pytest.raises(application_service.ApplicationInputError):
        application_service.create_application(db_session, job)


def test_create_application_duplicate_blocked_without_force(db_session, make_analyzed_job):
    from app.models.enums import ApplicationStatus

    job = make_analyzed_job()
    job.url = "https://careers.acme.com/apply/1"
    db_session.commit()
    first = application_service.create_application(db_session, job)
    first.status = ApplicationStatus.SUBMITTED
    db_session.commit()

    with pytest.raises(application_service.DuplicateApplicationError) as exc_info:
        application_service.create_application(db_session, job)
    assert exc_info.value.existing_application_id == first.id


def test_create_application_duplicate_allowed_with_force(db_session, make_analyzed_job):
    from app.models.enums import ApplicationStatus

    job = make_analyzed_job()
    job.url = "https://careers.acme.com/apply/1"
    db_session.commit()
    first = application_service.create_application(db_session, job)
    first.status = ApplicationStatus.SUBMITTED
    db_session.commit()

    second = application_service.create_application(db_session, job, force=True)
    assert second.id != first.id


# --- application_service: approval / pause / resume / user input -------------


def test_approve_submission_sets_flag_and_status(db_session, make_analyzed_job):
    job = make_analyzed_job()
    job.url = "https://careers.acme.com/apply/1"
    db_session.commit()
    application = application_service.create_application(db_session, job)

    approved = application_service.approve_submission(db_session, application)
    assert approved.submission_approved is True
    assert approved.status.value == "approved_for_submission"


def test_pause_and_resume_change_status(db_session, make_analyzed_job):
    job = make_analyzed_job()
    job.url = "https://careers.acme.com/apply/1"
    db_session.commit()
    application = application_service.create_application(db_session, job)

    paused = application_service.pause(db_session, application)
    assert paused.status.value == "needs_user_input"
    resumed = application_service.resume(db_session, application)
    assert resumed.status.value == "filling"


async def test_provide_user_input_stores_value_on_field(db_session, make_analyzed_job):
    """No browser session is open here, so provide_user_input() falls
    back to updating the DB row alone -- the live-page write only
    happens when browser_manager has an active session for the
    application (see test_browser_application_e2e.py for that path)."""

    from app.models.application_field import ApplicationField

    job = make_analyzed_job()
    job.url = "https://careers.acme.com/apply/1"
    db_session.commit()
    application = application_service.create_application(db_session, job)

    field_row = ApplicationField(
        application_id=application.id, field_identifier="salary", label="Expected Salary",
        field_type=ApplicationFieldType.TEXT, status=ApplicationFieldStatus.NEEDS_REVIEW, user_review_required=True,
    )
    db_session.add(field_row)
    db_session.commit()
    db_session.refresh(field_row)

    updated = await application_service.provide_user_input(db_session, application, field_row.id, "$120,000")
    assert updated.final_value == "$120,000"
    assert updated.mapped_source == "user_input"
    assert updated.status.value == "filled"
    assert updated.user_review_required is False


async def test_provide_user_input_rejects_field_from_different_application(db_session, make_analyzed_job):
    from app.models.application_field import ApplicationField

    job = make_analyzed_job()
    job.url = "https://careers.acme.com/apply/1"
    db_session.commit()
    app1 = application_service.create_application(db_session, job)
    app2 = application_service.create_application(db_session, job, force=True)

    field_row = ApplicationField(
        application_id=app1.id, field_identifier="f", label="F",
        field_type=ApplicationFieldType.TEXT, status=ApplicationFieldStatus.DETECTED,
    )
    db_session.add(field_row)
    db_session.commit()
    db_session.refresh(field_row)

    with pytest.raises(application_service.ApplicationInputError):
        await application_service.provide_user_input(db_session, app2, field_row.id, "value")


# --- event logging -------------------------------------------------------------


def test_create_application_logs_an_event(db_session, make_analyzed_job):
    from app.models.application_event import ApplicationEvent

    job = make_analyzed_job()
    job.url = "https://careers.acme.com/apply/1"
    db_session.commit()
    application = application_service.create_application(db_session, job)

    events = db_session.query(ApplicationEvent).filter_by(application_id=application.id).all()
    assert len(events) == 1
    assert events[0].event_type.value == "application_created"
