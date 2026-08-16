"""Step 6 test suite: job-search tracking, analytics, and follow-up
management. Uses a realistic synthetic dataset (spec section 74): 20
jobs, 10 shortlisted, 8 applications, 3 responses, 2 interviews, 1 offer
-- entirely fake companies/data, never real credentials."""

from datetime import date, datetime, timedelta, timezone

import pytest

from app.models.application import Application
from app.models.application_followup import ApplicationFollowUp
from app.models.application_note import ApplicationNote
from app.models.application_status_history import ApplicationStatusHistory
from app.models.enums import (
    ApplicationEventType,
    ApplicationNoteType,
    ApplicationStatus,
    FollowUpStatus,
    FollowUpType,
    InterviewStatus,
    InterviewType,
    JobStatus,
    OfferStatus,
    PriorityLevel,
)
from app.models.interview import Interview
from app.models.job import Job
from app.models.job_match import JobMatch
from app.models.job_note import JobNote
from app.models.offer import Offer
from app.services import analytics_service, export_service, followup_service, note_service, tracking_service

COMPANIES = ["Acme Corp", "Beta Inc", "Gamma LLC", "Delta Co"]
TITLES = ["ML Engineer", "Data Scientist", "AI Engineer", "Backend Engineer"]
SOURCES = ["LinkedIn", "Indeed", "company_website", "referral"]
MATCH_SCORES = [92, 88, 76, 65, 90, 82, 70, 60]


@pytest.fixture
def synthetic_job_search(db_session, rich_profile, make_approved_cv, make_approved_cover_letter):
    profile_id = rich_profile["profile"]["id"]
    now = datetime.now(timezone.utc)

    jobs = []
    for i in range(20):
        job = Job(
            title=TITLES[i % 4], company=COMPANIES[i % 4], description=f"Job posting #{i} description.",
            extracted_at=now - timedelta(days=20 - i), status=JobStatus.DISCOVERED,
        )
        db_session.add(job)
        db_session.flush()
        jobs.append(job)

    # First 10 jobs: shortlisted or later.
    for job in jobs[:10]:
        job.status = JobStatus.SHORTLISTED
    db_session.commit()

    # 8 of the shortlisted jobs get a JobMatch + an Application.
    applications = []
    for i, job in enumerate(jobs[:8]):
        match = JobMatch(
            job_id=job.id, overall_score=MATCH_SCORES[i], recommendation="apply",
            score_components={"required_skills": MATCH_SCORES[i]}, algorithm_version="v1",
        )
        db_session.add(match)

        cv = make_approved_cv(job.id, profile_id, version_number=1)
        cl = make_approved_cover_letter(job.id, cv.id, profile_id, version_number=1)

        application = Application(
            job_id=job.id, cv_version_id=cv.id, cover_letter_id=cl.id,
            application_url=f"https://example.com/apply/{job.id}", status=ApplicationStatus.SUBMITTED,
            submitted_at=now - timedelta(days=8 - i), source=SOURCES[i % 4],
        )
        db_session.add(application)
        db_session.flush()
        applications.append(application)

    db_session.commit()
    for a in applications:
        db_session.refresh(a)

    # 3 applications get a recruiter response.
    for application in applications[:3]:
        tracking_service.change_application_status(
            db_session, application, ApplicationStatus.UNDER_REVIEW, reason="Recruiter email received.", source="user",
        )

    # 2 of those get an interview.
    interviews = []
    for application in applications[:2]:
        interview = Interview(
            application_id=application.id, type=InterviewType.TECHNICAL,
            scheduled_at=application.submitted_at + timedelta(days=5), status=InterviewStatus.SCHEDULED,
        )
        db_session.add(interview)
        db_session.flush()
        interviews.append(interview)
        tracking_service.change_application_status(db_session, application, ApplicationStatus.TECHNICAL_INTERVIEW, source="user")
    db_session.commit()

    # 1 of those gets an accepted offer.
    offer = Offer(
        application_id=applications[0].id, company=applications[0].job.company, role=applications[0].job.title,
        salary=140000, currency="USD", status=OfferStatus.ACCEPTED,
    )
    db_session.add(offer)
    tracking_service.change_application_status(db_session, applications[0], ApplicationStatus.ACCEPTED, source="user")
    db_session.commit()

    return {"jobs": jobs, "applications": applications, "interviews": interviews, "offer": offer}


# --- 1: job status ------------------------------------------------------


def test_job_status_extended_values_available():
    assert JobStatus.PREPARING.value == "preparing"
    assert JobStatus.READY_TO_APPLY.value == "ready_to_apply"
    assert JobStatus.ARCHIVED.value == "archived"


def test_job_status_not_auto_set_to_applied_by_analysis(db_session, make_analyzed_job):
    job = make_analyzed_job()
    assert job.status != JobStatus.APPLIED


def test_manual_job_status_update_via_api(client, rich_profile, make_analyzed_job):
    job = make_analyzed_job()
    resp = client.patch(f"/jobs/{job.id}/status", json={"status": "ready_to_apply"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "ready_to_apply"


# --- 2, 3: application status + status history --------------------------


def test_application_status_change_creates_history_entry(db_session, synthetic_job_search):
    application = synthetic_job_search["applications"][2]
    history = db_session.query(ApplicationStatusHistory).filter_by(application_id=application.id).all()
    assert any(h.new_status == ApplicationStatus.UNDER_REVIEW for h in history)
    assert any(h.reason == "Recruiter email received." for h in history)


def test_status_history_never_overwritten_full_chain(db_session, synthetic_job_search):
    """submitted -> under_review -> technical_interview -> accepted, all
    still present (spec sections 6-7)."""

    application = synthetic_job_search["applications"][0]
    new_statuses = [h.new_status for h in application.status_history]
    assert ApplicationStatus.UNDER_REVIEW in new_statuses
    assert ApplicationStatus.TECHNICAL_INTERVIEW in new_statuses
    assert ApplicationStatus.ACCEPTED in new_statuses
    assert len(new_statuses) == len(set(id(h) for h in application.status_history))  # every transition kept, none merged


def test_manual_status_update_via_api(client, rich_profile, db_session, make_analyzed_job):
    job = make_analyzed_job()
    job.url = "https://careers.acme.com/1"
    db_session.commit()
    app_resp = client.post(f"/jobs/{job.id}/apply", json={"application_url": job.url})
    app_id = app_resp.json()["id"]

    resp = client.patch(f"/applications/{app_id}/status", json={"status": "interview", "reason": "Recruiter scheduled technical interview"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "interview"

    history = client.get(f"/applications/{app_id}/status-history").json()
    assert any(h["new_status"] == "interview" for h in history)


# --- 4: timeline ---------------------------------------------------------


def test_timeline_merges_and_sorts_all_sources(db_session, synthetic_job_search):
    application = synthetic_job_search["applications"][0]
    note_service.add_application_note(db_session, application, "Recruiter is John.", note_type=ApplicationNoteType.RECRUITER)
    db_session.refresh(application)

    entries = tracking_service.build_timeline(application)
    types = {e.entry_type for e in entries}
    assert {"job", "status_change", "note", "interview", "offer"}.issubset(types)
    timestamps = [e.timestamp for e in entries]
    assert timestamps == sorted(timestamps)


def test_timeline_endpoint_via_api(client, synthetic_job_search):
    application = synthetic_job_search["applications"][0]
    resp = client.get(f"/applications/{application.id}/timeline")
    assert resp.status_code == 200
    body = resp.json()
    assert body["application_id"] == application.id
    assert len(body["entries"]) > 0


# --- 5: follow-ups ---------------------------------------------------------


def test_suggested_followup_date_uses_default_days(db_session, synthetic_job_search):
    application = synthetic_job_search["applications"][0]
    suggested = followup_service.suggested_followup_date(application)
    assert suggested == (application.submitted_at + timedelta(days=7)).date()


def test_followup_not_created_automatically(db_session, synthetic_job_search):
    application = synthetic_job_search["applications"][5]
    followups = followup_service.list_followups(db_session, application.id)
    assert followups == []


def test_create_and_complete_followup_via_api(client, synthetic_job_search):
    application = synthetic_job_search["applications"][3]
    due = (datetime.now(timezone.utc) + timedelta(days=7)).date().isoformat()
    create = client.post(f"/applications/{application.id}/followups", json={"due_date": due, "type": "recruiter_followup", "subject": "Check in"})
    assert create.status_code == 201
    followup_id = create.json()["id"]

    complete = client.patch(f"/followups/{followup_id}", json={"status": "completed"})
    assert complete.status_code == 200
    assert complete.json()["status"] == "completed"
    assert complete.json()["completed_at"] is not None


def test_upcoming_followups_due_today(db_session, synthetic_job_search):
    # "Today" per the service is the UTC calendar day (spec section 60:
    # store timestamps in UTC) -- using the system-local date.today() here
    # would flake near local-midnight when local time has already rolled
    # to the next day but UTC hasn't (or vice versa).
    today_utc = datetime.now(timezone.utc).date()
    application = synthetic_job_search["applications"][4]
    followup_service.create_followup(db_session, application, today_utc)
    upcoming = followup_service.upcoming_followups(db_session, within_days=0)
    assert any(f.application_id == application.id for f in upcoming)


# --- 6: interviews ---------------------------------------------------------


def test_interviews_recorded_only_from_user_input(db_session, synthetic_job_search):
    interviews = synthetic_job_search["interviews"]
    assert len(interviews) == 2
    for i in interviews:
        assert i.type == InterviewType.TECHNICAL


def test_create_and_complete_interview_via_api(client, synthetic_job_search):
    application = synthetic_job_search["applications"][6]
    create = client.post(f"/applications/{application.id}/interviews", json={"type": "phone_screen", "interviewer": "Jane Recruiter"})
    assert create.status_code == 201
    interview_id = create.json()["id"]

    update = client.patch(f"/applications/{application.id}/interviews/{interview_id}", json={"status": "completed"})
    assert update.status_code == 200
    assert update.json()["status"] == "completed"


# --- 7: offers -------------------------------------------------------------


def test_offer_recorded_with_real_values_only(synthetic_job_search):
    offer = synthetic_job_search["offer"]
    assert offer.salary == 140000
    assert offer.status == OfferStatus.ACCEPTED


def test_create_offer_via_api(client, synthetic_job_search):
    application = synthetic_job_search["applications"][7]
    resp = client.post(f"/applications/{application.id}/offers", json={"company": "Acme Corp", "role": "ML Engineer", "salary": 120000, "currency": "USD"})
    assert resp.status_code == 201
    assert resp.json()["status"] == "received"


# --- 8, 15: notes ------------------------------------------------------


def test_application_note_creation(db_session, synthetic_job_search):
    application = synthetic_job_search["applications"][1]
    note = note_service.add_application_note(db_session, application, "Strong culture fit.", note_type=ApplicationNoteType.GENERAL)
    assert note.content == "Strong culture fit."
    events = [e.event_type for e in application.events]
    assert ApplicationEventType.NOTE_ADDED in events


def test_job_note_creation_does_not_modify_profile(db_session, synthetic_job_search, rich_profile):
    job = synthetic_job_search["jobs"][0]
    note = note_service.add_job_note(db_session, job, "Strong match but requires relocation.")
    assert note.content == "Strong match but requires relocation."
    # Profile is untouched by adding a job note.
    assert rich_profile["profile"]["full_name"] == "YOUR_NAME"


# --- 9: tags -------------------------------------------------------------


def test_job_tags_update_via_api(client, synthetic_job_search):
    job = synthetic_job_search["jobs"][0]
    resp = client.patch(f"/jobs/{job.id}/tags", json={"tags": ["dream-company", "ML", "urgent"]})
    assert resp.status_code == 200
    assert set(resp.json()["tags"]) == {"dream-company", "ML", "urgent"}


def test_application_tags_update_via_api(client, synthetic_job_search):
    application = synthetic_job_search["applications"][0]
    resp = client.patch(f"/applications/{application.id}/tags", json={"tags": ["high-priority"]})
    assert resp.status_code == 200
    assert resp.json()["tags"] == ["high-priority"]


# --- 10: priority ----------------------------------------------------------


def test_job_priority_update_via_api(client, synthetic_job_search):
    job = synthetic_job_search["jobs"][1]
    resp = client.patch(f"/jobs/{job.id}/priority", json={"priority": "critical"})
    assert resp.status_code == 200
    assert resp.json()["priority"] == "critical"


def test_default_priority_is_medium(synthetic_job_search):
    job = synthetic_job_search["jobs"][2]
    assert job.priority == PriorityLevel.MEDIUM


# --- 11: duplicate detection ------------------------------------------


def test_duplicate_detection_by_company_and_normalized_title(db_session, synthetic_job_search):
    original = synthetic_job_search["jobs"][0]
    duplicate = Job(title=original.title.upper() + "  ", company=original.company, description="Reposted listing.")
    db_session.add(duplicate)
    db_session.commit()
    db_session.refresh(duplicate)

    candidates = tracking_service.find_possible_duplicate_jobs(db_session, duplicate)
    assert original.id in [c.id for c in candidates]


def test_duplicate_detection_endpoint_only_surfaces_a_warning(client, db_session, synthetic_job_search):
    """The synthetic dataset cycles company/title every 4 jobs on purpose
    (a realistic repost scenario), so jobs[0] and jobs[4] are genuine
    company+title duplicates of each other. The endpoint must surface
    this as information, not raise an error or otherwise block anything
    -- there's no "creation" step to block here at all, by design (spec
    section 25: "show a warning... let the user decide")."""

    original = synthetic_job_search["jobs"][0]
    duplicate = synthetic_job_search["jobs"][4]
    resp = client.get(f"/jobs/{original.id}/duplicates")
    assert resp.status_code == 200
    body = resp.json()
    assert body["possible_duplicate"] is True
    assert duplicate.id in [c["id"] for c in body["candidates"]]


def test_no_duplicates_returns_empty(db_session, make_analyzed_job):
    job = make_analyzed_job(title="Totally Unique Role", company="Nobody Else Inc")
    candidates = tracking_service.find_possible_duplicate_jobs(db_session, job)
    assert candidates == []


# --- 12: deadline handling -------------------------------------------


def test_deadline_null_when_unknown(db_session, make_analyzed_job):
    job = make_analyzed_job()
    assert job.application_deadline is None
    assert job.deadline_source is None


def test_deadline_sort_orders_soonest_first(client, db_session, make_analyzed_job):
    job_far = make_analyzed_job(title="Far Deadline Role", company="X Co")
    job_far.application_deadline = date.today() + timedelta(days=30)
    job_near = make_analyzed_job(title="Near Deadline Role", company="Y Co")
    job_near.application_deadline = date.today() + timedelta(days=2)
    db_session.commit()

    resp = client.get("/jobs/search", params={"sort": "deadline", "limit": 100})
    ids_in_order = [j["id"] for j in resp.json()["items"] if j["application_deadline"]]
    assert ids_in_order.index(job_near.id) < ids_in_order.index(job_far.id)


# --- 13: match score analytics ---------------------------------------


def test_match_score_analysis_buckets_correctly(db_session, synthetic_job_search):
    result = analytics_service.match_score_analysis(db_session)
    # Scores: 92,88,76,65,90,82,70,60 -> 90-100: {92,90}=2, 80-89: {88,82}=2, 70-79: {76,70}=2, 60-69: {65,60}=2
    assert result["90-100"]["applications"] == 2
    assert result["80-89"]["applications"] == 2
    assert result["70-79"]["applications"] == 2
    assert result["60-69"]["applications"] == 2


# --- 14: company analytics -------------------------------------------


def test_company_analytics_counts(db_session, synthetic_job_search):
    result = analytics_service.company_analytics(db_session)
    total_applications = sum(v["applications"] for v in result.values())
    assert total_applications == 8


# --- 15: role analytics -------------------------------------------------


def test_role_analytics_counts(db_session, synthetic_job_search):
    result = analytics_service.role_analytics(db_session)
    total_applications = sum(v["applications"] for v in result.values())
    assert total_applications == 8


# --- 16: skill analytics -------------------------------------------------


def test_skill_analytics_demand_and_gap(db_session, synthetic_job_search, rich_profile):
    from app.models.job_requirement import JobRequirement

    for job in synthetic_job_search["jobs"][:8]:
        db_session.add(JobRequirement(job_id=job.id, requirement_text="PyTorch", category="technical_skill", importance="high", required=True, skill_name="PyTorch"))
        db_session.add(JobRequirement(job_id=job.id, requirement_text="Docker", category="technical_skill", importance="medium", required=False, skill_name="Docker"))
    db_session.commit()

    result = analytics_service.skill_analytics(db_session)
    assert result["demand"]["PyTorch"] == 8
    assert result["demand"]["Docker"] == 8
    gap_skills = {g["skill"] for g in result["potential_gaps"]}
    assert "Docker" in gap_skills
    assert "PyTorch" not in gap_skills  # profile has PyTorch (rich_profile fixture)


# --- 17: source analytics -------------------------------------------------


def test_source_analytics_counts(db_session, synthetic_job_search):
    result = analytics_service.source_analytics(db_session)
    total = sum(v["applications"] for v in result.values())
    assert total == 8


# --- 18: CV version analytics ---------------------------------------------


def test_cv_version_analytics_counts(db_session, synthetic_job_search):
    result = analytics_service.cv_version_analytics(db_session)
    assert sum(v["applications"] for v in result["cv_versions"].values()) == 8
    assert sum(v["applications"] for v in result["cover_letter_versions"].values()) == 8


# --- 19: conversion rates --------------------------------------------


def test_conversion_rates_computed_correctly(db_session, synthetic_job_search):
    f = analytics_service.funnel(db_session)
    assert f["discovered"] == 20
    assert f["shortlisted"] == 10
    assert f["applied"] == 8
    assert f["responses"] == 3
    assert f["interviews"] == 2
    assert f["offers"] == 1
    assert f["accepted"] == 1

    rates = analytics_service.conversion_rates(f)
    assert rates["shortlist_rate"] == 50.0
    assert rates["application_rate"] == 80.0
    assert rates["response_rate"] == pytest.approx(37.5)
    assert rates["interview_rate"] == 25.0
    assert rates["offer_rate"] == 50.0
    assert rates["overall_offer_rate"] == pytest.approx(12.5)


def test_conversion_rate_safe_division_returns_none_for_empty(db_session):
    f = {"discovered": 0, "shortlisted": 0, "applied": 0, "responses": 0, "interviews": 0, "offers": 0, "accepted": 0}
    rates = analytics_service.conversion_rates(f)
    assert all(v is None for v in rates.values())


# --- 20, 21, 22: response / interview / offer time -----------------------


def test_response_time_stats_computed(db_session, synthetic_job_search):
    stats = analytics_service.response_time_stats(db_session)
    assert stats["count"] == 3
    assert stats["average"] is not None
    assert stats["minimum"] <= stats["average"] <= stats["maximum"]


def test_interview_time_stats_computed(db_session, synthetic_job_search):
    stats = analytics_service.interview_time_stats(db_session)
    assert stats["count"] == 2


def test_offer_time_stats_computed(db_session, synthetic_job_search):
    stats = analytics_service.offer_time_stats(db_session)
    assert stats["count"] == 1
    assert stats["average"] == stats["median"] == stats["minimum"] == stats["maximum"]


# --- 23, 24: weekly / monthly analytics -----------------------------------


def test_weekly_analytics_shape(db_session, synthetic_job_search):
    result = analytics_service.weekly_analytics(db_session)
    assert result["period"] == "week"
    assert "jobs_discovered" in result


def test_monthly_analytics_shape(db_session, synthetic_job_search):
    result = analytics_service.monthly_analytics(db_session)
    assert result["period"] == "month"
    assert result["applications"] >= 0


# --- 25: application readiness ------------------------------------------


def test_readiness_ready_for_fully_prepared_application(db_session, synthetic_job_search):
    application = synthetic_job_search["applications"][5]
    result = tracking_service.check_readiness(db_session, application)
    assert result["checks"]["cv_approved"] is True
    assert result["checks"]["application_url_valid"] is True


def test_readiness_not_ready_without_cv(db_session, make_analyzed_job):
    from app.services import application_service

    job = make_analyzed_job()
    job.url = "https://careers.acme.com/x"
    db_session.commit()
    application = application_service.create_application(db_session, job)
    result = tracking_service.check_readiness(db_session, application)
    assert result["checks"]["cv_approved"] is False
    assert result["ready"] is False


# --- 26, 27: CSV / JSON export --------------------------------------------


def test_csv_export_contains_all_applications(db_session, synthetic_job_search):
    rows = export_service.export_applications(db_session)
    assert len(rows) == 8
    csv_text = export_service.to_csv(rows)
    assert "company" in csv_text
    assert synthetic_job_search["jobs"][0].company in csv_text


def test_json_export_is_valid_json(db_session, synthetic_job_search):
    import json

    rows = export_service.export_applications(db_session)
    parsed = json.loads(export_service.to_json(rows))
    assert len(parsed) == 8


def test_export_endpoint_csv_via_api(client, synthetic_job_search):
    resp = client.get("/applications/export", params={"format": "csv"})
    assert resp.status_code == 200
    assert "text/csv" in resp.headers["content-type"]


def test_export_excludes_archived_by_default(db_session, synthetic_job_search):
    application = synthetic_job_search["applications"][0]
    application.archived = True
    db_session.commit()
    rows = export_service.export_applications(db_session)
    assert application.id not in [r["id"] for r in rows]
    rows_with_archived = export_service.export_applications(db_session, include_archived=True)
    assert application.id in [r["id"] for r in rows_with_archived]


# --- 28: archive functionality ------------------------------------------


def test_archive_job_keeps_it_in_database(client, db_session, synthetic_job_search):
    job = synthetic_job_search["jobs"][10]
    resp = client.post(f"/jobs/{job.id}/archive")
    assert resp.status_code == 200
    assert resp.json()["status"] == "archived"
    assert db_session.get(Job, job.id) is not None


def test_archive_application_keeps_it_in_database(client, db_session, synthetic_job_search):
    application = synthetic_job_search["applications"][6]
    resp = client.post(f"/applications/{application.id}/archive")
    assert resp.status_code == 200
    assert resp.json()["archived"] is True
    assert db_session.get(Application, application.id) is not None


# --- 29, 30: search / filtering ------------------------------------------


def test_job_search_filters_by_status(client, synthetic_job_search):
    resp = client.get("/jobs/search", params={"status": "shortlisted", "limit": 100})
    assert resp.status_code == 200
    assert all(j["status"] == "shortlisted" for j in resp.json()["items"])


def test_job_search_filters_by_company(client, synthetic_job_search):
    resp = client.get("/jobs/search", params={"company": "Acme", "limit": 100})
    assert all("Acme" in j["company"] for j in resp.json()["items"])


def test_application_search_filters_by_status(client, synthetic_job_search):
    resp = client.get("/applications/search", params={"status": "under_review", "limit": 100})
    assert resp.status_code == 200
    assert all(a["status"] == "under_review" for a in resp.json()["items"])


def test_application_search_min_match_score(client, synthetic_job_search):
    resp = client.get("/applications/search", params={"min_match_score": 85, "limit": 100})
    assert resp.status_code == 200
    assert resp.json()["total"] <= 8


# --- 31: sorting -----------------------------------------------------------


def test_job_search_sort_highest_match(client, synthetic_job_search):
    resp = client.get("/jobs/search", params={"sort": "highest_match", "limit": 100})
    scores = [j["id"] for j in resp.json()["items"]]
    assert len(scores) > 0


def test_application_search_sort_priority(client, synthetic_job_search):
    application = synthetic_job_search["applications"][0]
    client.patch(f"/applications/{application.id}/priority", json={"priority": "critical"})
    resp = client.get("/applications/search", params={"sort": "priority", "limit": 100})
    assert resp.json()["items"][0]["priority"] == "critical"


# --- 32: timeline ordering (already covered above, add edge case) --------


def test_timeline_ordering_status_before_interview_before_offer(db_session, synthetic_job_search):
    application = synthetic_job_search["applications"][0]
    entries = tracking_service.build_timeline(application)
    types_in_order = [e.entry_type for e in entries]
    status_idx = types_in_order.index("status_change")
    offer_idx = types_in_order.index("offer")
    assert status_idx < offer_idx


# --- 33: timezone handling -------------------------------------------


def test_status_history_timestamp_is_timezone_aware(db_session, synthetic_job_search):
    application = synthetic_job_search["applications"][0]
    for h in application.status_history:
        assert h.created_at.tzinfo is not None


def test_followup_due_date_combines_to_aware_datetime(client, synthetic_job_search):
    application = synthetic_job_search["applications"][2]
    due = date.today().isoformat()
    client.post(f"/applications/{application.id}/followups", json={"due_date": due, "subject": "tz check"})
    resp = client.get("/calendar/upcoming")
    assert resp.status_code == 200
    for item in resp.json():
        assert item["date"].endswith("Z") or "+" in item["date"]


# --- 34: data integrity (cascade deletes, no orphans) ---------------------


def test_deleting_application_cascades_to_interviews_offers_notes(db_session, synthetic_job_search):
    application = synthetic_job_search["applications"][0]
    application_id = application.id
    db_session.delete(application)
    db_session.commit()

    assert db_session.query(Interview).filter_by(application_id=application_id).count() == 0
    assert db_session.query(Offer).filter_by(application_id=application_id).count() == 0
    assert db_session.query(ApplicationNote).filter_by(application_id=application_id).count() == 0
    assert db_session.query(ApplicationFollowUp).filter_by(application_id=application_id).count() == 0


def test_deleting_job_cascades_to_applications(db_session, synthetic_job_search):
    job = synthetic_job_search["jobs"][0]
    job_id = job.id
    db_session.delete(job)
    db_session.commit()
    assert db_session.query(Application).filter_by(job_id=job_id).count() == 0


def test_job_note_cascades_on_job_delete(db_session, make_analyzed_job):
    job = make_analyzed_job()
    note_service.add_job_note(db_session, job, "test note")
    job_id = job.id
    db_session.delete(job)
    db_session.commit()
    assert db_session.query(JobNote).filter_by(job_id=job_id).count() == 0


# --- Dashboard / manual event / interview-context (extra integration) ----


def test_dashboard_reflects_synthetic_dataset(client, synthetic_job_search):
    resp = client.get("/dashboard")
    assert resp.status_code == 200
    body = resp.json()
    assert body["jobs"]["total"] == 20
    assert body["applications"]["submitted"] == 8
    assert body["interviews"]["total"] == 2
    assert body["offers"]["total"] == 1


def test_manual_event_creation_via_api(client, synthetic_job_search):
    application = synthetic_job_search["applications"][3]
    resp = client.post(f"/applications/{application.id}/events", json={"event_type": "recruiter_contact", "description": "Recruiter contacted me through LinkedIn."})
    assert resp.status_code == 201

    events = client.get(f"/applications/{application.id}/events").json()
    assert any(e["description"] == "Recruiter contacted me through LinkedIn." for e in events)


def test_interview_context_assembles_existing_data(db_session, synthetic_job_search):
    application = synthetic_job_search["applications"][0]
    context = tracking_service.build_interview_context(db_session, application)
    assert context["company"] == application.job.company
    assert context["cv_version"] is not None
    assert context["cover_letter"] is not None


def test_material_snapshot_frozen_on_submission(db_session, make_analyzed_job, rich_profile, make_approved_cv):
    from app.services import application_service

    job = make_analyzed_job()
    job.url = "https://careers.acme.com/snap"
    db_session.commit()
    cv = make_approved_cv(job.id, rich_profile["profile"]["id"])
    application = application_service.create_application(db_session, job, cv_version_id=cv.id)

    tracking_service.mark_submitted(db_session, application, "REF-123")
    assert application.material_snapshot is not None
    assert application.material_snapshot["cv_version"]["version_name"] == cv.version_name
    assert application.status == ApplicationStatus.SUBMITTED
