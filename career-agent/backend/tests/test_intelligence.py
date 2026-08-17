"""Step 7 test suite: job-search intelligence, optimization, and
recommendations. Uses a realistic synthetic dataset (spec section 63):
50 jobs, 30 shortlisted, 25 applications, 8 responses, 5 interviews, 2
offers, multiple CV versions/sources/roles/skill gaps/rejection reasons
-- entirely fake companies/data."""

from datetime import date, datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from app.ai.interview_prep_outputs import InterviewAnswerOutput, InterviewQuestionsOutput, InterviewQuestionOutput
from app.ai.recommendation_outputs import ExplanationOutput
from app.intelligence import (
    career_insights,
    cv_analyzer,
    interview_analyzer,
    job_prioritizer,
    recommendation_explainer,
    rejection_analyzer,
    skill_gap_analyzer,
)
from app.intelligence.confidence import confidence_from_sample_size
from app.models.application import Application
from app.models.cover_letter import CoverLetter
from app.models.cv_version import CVVersion
from app.models.enums import (
    ApplicationMaterialStatus,
    ApplicationStatus,
    InterviewType,
    JobStatus,
    OfferStatus,
    RejectionReason,
)
from app.models.interview import Interview
from app.models.job import Job
from app.models.job_match import JobMatch
from app.models.job_requirement import JobRequirement
from app.models.offer import Offer
from app.models.recommendation import Recommendation
from app.services import goal_service, recommendation_engine

COMPANIES = ["Acme Corp", "Beta Inc", "Gamma LLC", "Delta Co", "Epsilon AI"]
TITLES = ["ML Engineer", "Data Scientist", "AI Engineer", "Backend Engineer", "Computer Vision Engineer"]
SOURCES = ["LinkedIn", "Indeed", "company_website", "referral"]
CV_VERSION_NAMES = ["Test CV V1", "Test CV V2", "Test CV V3"]
MATCH_SCORES = [92, 88, 76, 65, 90, 82, 70, 60, 95, 55, 78, 68, 85, 91, 72, 63, 89, 74, 66, 80, 93, 58, 77, 84, 61]
REJECTION_REASONS = [RejectionReason.SKILLS_GAP, RejectionReason.INSUFFICIENT_EXPERIENCE, RejectionReason.NO_RESPONSE, None]


@pytest.fixture
def synthetic_dataset(db_session, rich_profile, make_approved_cover_letter):
    profile_id = rich_profile["profile"]["id"]
    now = datetime.now(timezone.utc)

    jobs = []
    for i in range(50):
        job = Job(
            title=TITLES[i % 5], company=COMPANIES[i % 5], description=f"Job posting #{i}.",
            source=SOURCES[i % 4], extracted_at=now - timedelta(days=50 - i), status=JobStatus.DISCOVERED,
        )
        db_session.add(job)
        db_session.flush()
        db_session.add(JobRequirement(job_id=job.id, requirement_text="PyTorch", category="technical_skill", importance="high", required=True, skill_name="PyTorch"))
        db_session.add(JobRequirement(job_id=job.id, requirement_text="AWS", category="technical_skill", importance="critical", required=True, skill_name="AWS"))
        if i % 3 == 0:
            db_session.add(JobRequirement(job_id=job.id, requirement_text="Kubernetes", category="technical_skill", importance="medium", required=False, skill_name="Kubernetes"))
        jobs.append(job)
    db_session.commit()

    for job in jobs[:30]:
        job.status = JobStatus.SHORTLISTED
    db_session.commit()

    cv_versions = []
    for i, name in enumerate(CV_VERSION_NAMES):
        # Use distinct jobs to own each CV version row (CVVersion.job_id is required).
        cv = CVVersion(
            job_id=jobs[i].id, profile_id=profile_id, version_name=name, version_number=1,
            template_name="ats/ml_engineer", status=ApplicationMaterialStatus.APPROVED,
        )
        db_session.add(cv)
        db_session.flush()
        cv_versions.append(cv)
    db_session.commit()

    applications = []
    for i, job in enumerate(jobs[:25]):
        match = JobMatch(job_id=job.id, overall_score=MATCH_SCORES[i], recommendation="apply", score_components={"required_skills": MATCH_SCORES[i]}, algorithm_version="v1")
        db_session.add(match)

        cv = cv_versions[i % 3]
        cl = make_approved_cover_letter(job.id, cv.id, profile_id, version_number=1)

        application = Application(
            job_id=job.id, cv_version_id=cv.id, cover_letter_id=cl.id,
            application_url=f"https://example.com/apply/{job.id}", status=ApplicationStatus.SUBMITTED,
            submitted_at=now - timedelta(days=25 - i), source=SOURCES[i % 4],
        )
        db_session.add(application)
        db_session.flush()
        applications.append(application)
    db_session.commit()
    for a in applications:
        db_session.refresh(a)

    # 8 responses.
    from app.services import tracking_service

    for application in applications[:8]:
        tracking_service.change_application_status(db_session, application, ApplicationStatus.UNDER_REVIEW, source="user")

    # 5 interviews (subset of the 8 responses).
    interviews = []
    for application in applications[:5]:
        interview = Interview(application_id=application.id, type=InterviewType.TECHNICAL, scheduled_at=application.submitted_at + timedelta(days=5), status="scheduled")
        db_session.add(interview)
        db_session.flush()
        interviews.append(interview)
        tracking_service.change_application_status(db_session, application, ApplicationStatus.TECHNICAL_INTERVIEW, source="user")
    db_session.commit()

    # 2 offers (subset of the 5 interviewed).
    offers = []
    for idx, application in enumerate(applications[:2]):
        offer = Offer(application_id=application.id, company=application.job.company, role=application.job.title, salary=130000 + idx * 10000, currency="USD", status=OfferStatus.ACCEPTED if idx == 0 else OfferStatus.RECEIVED)
        db_session.add(offer)
        offers.append(offer)
        tracking_service.change_application_status(db_session, application, ApplicationStatus.ACCEPTED if idx == 0 else ApplicationStatus.OFFER, source="user")
    db_session.commit()

    # Rejections: applications[8:14] (6 apps, none interviewed) marked rejected with varying reasons.
    for i, application in enumerate(applications[8:14]):
        tracking_service.change_application_status(db_session, application, ApplicationStatus.REJECTED, source="user")
        application.rejection_reason = REJECTION_REASONS[i % 4]
    db_session.commit()

    return {"jobs": jobs, "applications": applications, "cv_versions": cv_versions, "interviews": interviews, "offers": offers}


# --- 1: job priority -----------------------------------------------------


def test_job_priority_score_uses_real_factors(db_session, synthetic_dataset, rich_profile):
    from app.models.profile import CareerProfile

    profile = db_session.get(CareerProfile, rich_profile["profile"]["id"])
    job = synthetic_dataset["jobs"][0]
    breakdown = job_prioritizer.compute_priority(job, job.match, profile)
    assert 0 <= breakdown.score <= 100
    assert breakdown.reasons
    assert breakdown.confidence > 0


def test_job_priority_explains_every_score(db_session, synthetic_dataset, rich_profile):
    from app.models.profile import CareerProfile

    profile = db_session.get(CareerProfile, rich_profile["profile"]["id"])
    job = synthetic_dataset["jobs"][0]
    breakdown = job_prioritizer.compute_priority(job, job.match, profile)
    # WHAT+WHY+EVIDENCE+CONFIDENCE all present (spec section 5).
    assert breakdown.reasons and breakdown.confidence_reason and breakdown.factors


# --- 2: opportunity score -------------------------------------------------


def test_opportunity_score_never_framed_as_probability(db_session, synthetic_dataset):
    job = synthetic_dataset["jobs"][0]
    opp = job_prioritizer.compute_opportunity_score(job, job.match)
    assert 0 <= opp.score <= 100
    assert any("competit" in w.lower() for w in opp.warnings)


# --- 3: match-score analysis (reused from Step 6, sanity-checked here) ---


def test_match_score_buckets_available_for_intelligence(db_session, synthetic_dataset):
    from app.services.analytics_service import match_score_analysis

    result = match_score_analysis(db_session)
    total_applications = sum(v["applications"] for v in result.values())
    assert total_applications == 25


# --- 4: skill gaps ---------------------------------------------------------


def test_skill_gap_analysis_flags_missing_skill(db_session, synthetic_dataset, rich_profile):
    from app.models.profile import CareerProfile

    profile = db_session.get(CareerProfile, rich_profile["profile"]["id"])
    entries = skill_gap_analyzer.analyze_skill_gaps(db_session, profile)
    aws_entry = next(e for e in entries if e.skill == "AWS")
    assert aws_entry.has_skill is False
    assert aws_entry.priority in ("high", "medium", "low")

    pytorch_entry = next(e for e in entries if e.skill == "PyTorch")
    assert pytorch_entry.has_skill is True


def test_skill_gap_priority_uses_frequency_importance_relevance(db_session, synthetic_dataset, rich_profile):
    from app.models.profile import CareerProfile

    profile = db_session.get(CareerProfile, rich_profile["profile"]["id"])
    entries = skill_gap_analyzer.analyze_skill_gaps(db_session, profile)
    aws_entry = next(e for e in entries if e.skill == "AWS")
    assert aws_entry.priority_score == pytest.approx(aws_entry.demand_ratio * aws_entry.importance_score * aws_entry.relevance_score, rel=0.05)


# --- 5: CV performance (reused from Step 6) -------------------------------


def test_cv_version_performance_available(db_session, synthetic_dataset):
    from app.services.analytics_service import cv_version_analytics

    result = cv_version_analytics(db_session)
    assert sum(v["applications"] for v in result["cv_versions"].values()) == 25


def test_cv_analyzer_never_invents_skills(db_session, synthetic_dataset, rich_profile):
    from app.models.profile import CareerProfile

    profile = db_session.get(CareerProfile, rich_profile["profile"]["id"])
    cv = synthetic_dataset["cv_versions"][0]
    report = cv_analyzer.analyze_profile_vs_cv(profile, cv)
    for suggestion in report.suggestions:
        assert "if" in suggestion.lower() or "consider" in suggestion.lower() or "appear" in suggestion.lower()


# --- 6: source performance -------------------------------------------------


def test_source_strategy_picks_best_observed_source(db_session, synthetic_dataset):
    result = career_insights.source_strategy(db_session)
    assert result.label in SOURCES
    assert "observed" in result.observation.lower() or "early signal" in result.observation.lower()


# --- 7: role performance ----------------------------------------------------


def test_role_strategy_picks_best_observed_role(db_session, synthetic_dataset):
    result = career_insights.role_strategy(db_session)
    assert result.label in TITLES


# --- 8: rejection analysis --------------------------------------------------


def test_rejection_analysis_finds_reason_breakdown(db_session, synthetic_dataset):
    analysis = rejection_analyzer.analyze_rejections(db_session)
    assert analysis.total_rejected == 6
    assert "skills_gap" in analysis.reason_breakdown
    assert analysis.observations


def test_rejection_analysis_never_claims_causation(db_session, synthetic_dataset):
    analysis = rejection_analyzer.analyze_rejections(db_session)
    for obs in analysis.observations:
        assert "causes" not in obs.lower() and "caused" not in obs.lower()


# --- 9: response analysis (reused from Step 6 conversion rates) ----------


def test_response_pattern_via_funnel(db_session, synthetic_dataset):
    from app.services.analytics_service import funnel

    f = funnel(db_session)
    assert f["applied"] == 25
    # "Response" includes a rejection (spec section 22 -- a rejection is
    # still a response): the 8 applications moved to under_review, plus
    # the 6 separately-rejected applications[8:14], none overlapping.
    assert f["responses"] == 14
    assert f["interviews"] == 5
    assert f["offers"] == 2


# --- 10: interview preparation ---------------------------------------------


def test_interview_preparation_output_uses_real_context(db_session, synthetic_dataset):
    application = synthetic_dataset["applications"][0]
    output = interview_analyzer.build_preparation_output(db_session, application)
    assert output.company == application.job.company
    assert output.top_technical_areas
    assert output.likely_question_areas


# --- 11: recommendation generation ------------------------------------------


def test_recommendation_generation_produces_evidence_backed_rows(db_session, synthetic_dataset):
    recs = recommendation_engine.generate_all(db_session)
    assert recs
    for rec in recs:
        assert rec.evidence
        assert rec.confidence_reason
        assert 0.0 <= rec.confidence <= 1.0


def test_recommendation_generation_idempotent(db_session, synthetic_dataset):
    recommendation_engine.generate_all(db_session)
    count_after_first = db_session.query(Recommendation).count()
    recommendation_engine.generate_all(db_session)
    count_after_second = db_session.query(Recommendation).count()
    assert count_after_first == count_after_second


# --- 12: recommendation confidence ------------------------------------------


def test_recommendation_confidence_matches_sample_size():
    high, _ = confidence_from_sample_size(50)
    low, _ = confidence_from_sample_size(3)
    assert high > low


# --- 13: small sample protection --------------------------------------------


def test_small_sample_protection_caps_confidence():
    confidence, reason = confidence_from_sample_size(3)
    assert confidence < 0.5
    assert "early signal" in reason.lower()


def test_small_sample_protection_in_rejection_analysis(db_session, make_analyzed_job, rich_profile):
    from app.models.application import Application as App
    from app.services import tracking_service

    job = make_analyzed_job()
    job.url = "https://x"
    db_session.commit()
    application = App(job_id=job.id, application_url=job.url, status=ApplicationStatus.SUBMITTED, submitted_at=datetime.now(timezone.utc))
    db_session.add(application)
    db_session.commit()
    tracking_service.change_application_status(db_session, application, ApplicationStatus.REJECTED, source="user")

    analysis = rejection_analyzer.analyze_rejections(db_session)
    assert analysis.confidence < 0.5


# --- 14: evidence tracking ---------------------------------------------


def test_every_recommendation_has_traceable_evidence(db_session, synthetic_dataset):
    recs = recommendation_engine.generate_all(db_session)
    for rec in recs:
        assert isinstance(rec.evidence, dict)
        assert len(rec.evidence) > 0


# --- 15: LLM output validation ----------------------------------------


def test_llm_explanation_strips_fabricated_statistics():
    evidence = {"applications": 15, "interviews": 5}
    fabricated = "This role shows a 33% interview rate. Also, 99% of hiring managers prefer this background."
    cleaned, discarded = recommendation_explainer.validate_explanation(fabricated, evidence)
    assert "99%" not in cleaned
    assert discarded


def test_llm_explanation_falls_back_when_ollama_unavailable():
    fake_client = MagicMock()
    fake_client.chat_structured.side_effect = RuntimeError("no ollama")
    result = recommendation_explainer.explain(fake_client, {"applications": 10}, fallback="Deterministic fallback text.")
    assert result["llm_used"] is False
    assert result["explanation"] == "Deterministic fallback text."


def test_llm_explanation_uses_llm_when_valid():
    fake_client = MagicMock()
    fake_client.chat_structured.return_value = ExplanationOutput(explanation="Based on 10 applications, this looks promising.")
    result = recommendation_explainer.explain(fake_client, {"applications": 10}, fallback="fallback")
    assert result["llm_used"] is True
    assert "10" in result["explanation"]


# --- 16: recommendation feedback --------------------------------------


def test_recommendation_feedback_via_api(client, synthetic_dataset):
    generate = client.post("/intelligence/recommendations/generate")
    assert generate.status_code == 200
    items = generate.json()["items"]
    assert items
    rec_id = items[0]["id"]

    accept = client.post(f"/intelligence/recommendations/{rec_id}/accept")
    assert accept.status_code == 200
    assert accept.json()["status"] == "accepted"

    dismiss = client.post(f"/intelligence/recommendations/{items[1]['id']}/dismiss")
    assert dismiss.json()["status"] == "dismissed"


def test_recommendation_view_marks_new_as_viewed(client, synthetic_dataset):
    generate = client.post("/intelligence/recommendations/generate")
    rec_id = generate.json()["items"][0]["id"]
    get_resp = client.get(f"/intelligence/recommendations/{rec_id}")
    assert get_resp.json()["status"] == "viewed"


# --- 17: weekly review -----------------------------------------------------


def test_weekly_review_has_all_required_fields(db_session, synthetic_dataset):
    review = career_insights.weekly_review(db_session)
    assert "recommendation" in review
    assert "period" in review


def test_weekly_review_via_api(client, synthetic_dataset):
    resp = client.get("/intelligence/weekly-review")
    assert resp.status_code == 200
    body = resp.json()
    assert "observations" in body and "recommendations" in body and "evidence" in body and "confidence" in body


# --- 18: career strategy ----------------------------------------------


def test_personalized_strategy_via_api(client, synthetic_dataset):
    resp = client.get("/intelligence/strategy")
    assert resp.status_code == 200
    body = resp.json()
    assert "strengths" in body and "weaknesses" in body and "suggested_weekly_targets" in body


def test_career_direction_never_commands(db_session, synthetic_dataset):
    direction = career_insights.career_direction(db_session)
    assert "you should become" not in direction.observation.lower()


# --- 19: user goal tracking -------------------------------------------


def test_goal_set_and_progress_via_api(client, synthetic_dataset):
    put_resp = client.put("/intelligence/goals", json={"applications_per_week": 10, "interviews_per_month": 3})
    assert put_resp.status_code == 200
    assert put_resp.json()["applications_per_week"] == 10

    progress = client.get("/intelligence/goals/progress")
    assert progress.status_code == 200
    body = progress.json()
    assert body["progress"]["applications_per_week"]["goal"] == 10


def test_goal_progress_never_shames(db_session, synthetic_dataset):
    goal = goal_service.set_goal(db_session, {"applications_per_week": 100})
    progress = goal_service.goal_progress(db_session, goal)
    assert progress["applications_per_week"]["percent"] <= 100  # capped, not a negative/shaming value


# --- 20: API endpoints -------------------------------------------------


def test_job_intelligence_endpoint(client, synthetic_dataset):
    job = synthetic_dataset["jobs"][0]
    resp = client.get(f"/intelligence/jobs/{job.id}")
    assert resp.status_code == 200
    body = resp.json()
    assert "priority" in body and "opportunity" in body and body["confidence"] >= 0


def test_application_intelligence_endpoint(client, synthetic_dataset):
    application = synthetic_dataset["applications"][0]
    resp = client.get(f"/intelligence/applications/{application.id}")
    assert resp.status_code == 200
    body = resp.json()
    assert "quality" in body and "interview_preparation" in body


def test_skill_endpoints(client, synthetic_dataset):
    assert client.get("/intelligence/skills").status_code == 200
    assert client.get("/intelligence/skills/gaps").status_code == 200
    assert client.get("/intelligence/skills/demand").status_code == 200


def test_career_endpoint(client, synthetic_dataset):
    resp = client.get("/intelligence/career")
    assert resp.status_code == 200
    body = resp.json()
    assert "recommended_target_roles" in body


def test_rejection_reason_endpoint(client, synthetic_dataset):
    application = synthetic_dataset["applications"][8]
    resp = client.patch(f"/applications/{application.id}/rejection-reason", json={"rejection_reason": "location"})
    assert resp.status_code == 200
    assert resp.json()["rejection_reason"] == "location"


def test_interview_prep_questions_endpoint_mocked(client, synthetic_dataset, mocker):
    application = synthetic_dataset["applications"][0]
    fake_client = MagicMock()
    fake_client.model = "test-model"
    fake_client.chat_structured.return_value = InterviewQuestionsOutput(questions=[
        InterviewQuestionOutput(question="Describe a PyTorch project.", category="technical"),
        InterviewQuestionOutput(question="Tell me about a challenge you faced.", category="behavioral"),
    ])
    mocker.patch("app.api.intelligence.get_ollama_client", return_value=fake_client)

    resp = client.post("/interview-prep/questions", json={"application_id": application.id})
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["questions"]) == 2
    assert "disclaimer" in body


def test_interview_prep_answer_endpoint_mocked(client, synthetic_dataset, rich_profile, mocker):
    application = synthetic_dataset["applications"][0]
    fake_client = MagicMock()
    fake_client.model = "test-model"
    fake_client.chat_structured.return_value = InterviewAnswerOutput(answer="I developed deep learning models for medical image segmentation using PyTorch at Acme AI.")
    mocker.patch("app.api.intelligence.get_ollama_client", return_value=fake_client)

    resp = client.post("/interview-prep/answer", json={"application_id": application.id, "question": "Tell me about your PyTorch experience."})
    assert resp.status_code == 200
    body = resp.json()
    assert body["validated"] is True
    assert body["answer"]


def test_interview_prep_answer_rejects_unsupported_claim(client, synthetic_dataset, rich_profile, mocker):
    application = synthetic_dataset["applications"][0]
    fake_client = MagicMock()
    fake_client.model = "test-model"
    fake_client.chat_structured.return_value = InterviewAnswerOutput(answer="I am an expert in Kubernetes with 10 years of production experience.")
    mocker.patch("app.api.intelligence.get_ollama_client", return_value=fake_client)

    resp = client.post("/interview-prep/answer", json={"application_id": application.id, "question": "Tell me about Kubernetes."})
    assert resp.status_code == 200
    body = resp.json()
    assert body["validated"] is False
    assert body["validation_issues"]
