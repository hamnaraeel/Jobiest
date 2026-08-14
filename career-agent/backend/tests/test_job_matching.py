from datetime import datetime, timezone

import pytest

from app.models.enums import MatchStatus, Recommendation, RequirementCategory, RequirementImportance
from app.models.job import Job
from app.models.job_requirement import JobRequirement
from app.services.job_matching_service import (
    DEFAULT_RECOMMENDATION_THRESHOLDS,
    MatchInputError,
    compute_match,
    evaluate_requirement,
    get_relevant_career_data,
    normalize_skill,
    score_to_recommendation,
    skills_equivalent,
)


def _make_job_with_requirements(db_session, reqs) -> Job:
    job = Job(title="ML Engineer", company="Acme", description="d", extracted_at=datetime.now(timezone.utc))
    db_session.add(job)
    db_session.flush()
    for r in reqs:
        db_session.add(JobRequirement(job_id=job.id, **r))
    db_session.commit()
    db_session.refresh(job)
    return job


# --- 8: skill normalization --------------------------------------------------


def test_normalize_skill_strips_suffix_words_and_case():
    assert normalize_skill("PyTorch Framework") == normalize_skill("pytorch")
    assert normalize_skill("PyTorch") == "pytorch"


def test_skills_equivalent_recognizes_alias_groups():
    assert skills_equivalent("Kubernetes", "k8s")
    assert skills_equivalent("PyTorch", "pytorch framework")
    assert skills_equivalent("Hugging Face Transformers", "Transformers")


def test_skills_not_equivalent_for_unrelated_tools():
    assert not skills_equivalent("Python", "Java")
    assert not skills_equivalent("PyTorch", "TensorFlow")
    assert not skills_equivalent("AWS", "Azure")
    assert not skills_equivalent("Docker", "Kubernetes")


# --- 9, 10, 11, 12: matched / partial / missing / unknown -------------------


def test_evaluate_requirement_matched_when_skill_verified(client, profile, db_session):
    client.post("/skills", json={"profile_id": profile["id"], "name": "PyTorch", "category": "ML/DL", "verified": True})
    ctx = get_relevant_career_data(db_session, profile["id"])
    req = JobRequirement(
        job_id=0, requirement_text="PyTorch", category=RequirementCategory.TECHNICAL_SKILL,
        importance=RequirementImportance.HIGH, required=True, skill_name="PyTorch",
    )
    result = evaluate_requirement(req, ctx)
    assert result.status == MatchStatus.MATCHED
    assert result.evidence


def test_evaluate_requirement_partial_when_skill_unverified(client, profile, db_session):
    client.post("/skills", json={"profile_id": profile["id"], "name": "Docker", "category": "Tool", "verified": False})
    ctx = get_relevant_career_data(db_session, profile["id"])
    req = JobRequirement(
        job_id=0, requirement_text="Docker", category=RequirementCategory.TECHNICAL_SKILL,
        importance=RequirementImportance.MEDIUM, required=False, skill_name="Docker",
    )
    result = evaluate_requirement(req, ctx)
    assert result.status == MatchStatus.PARTIAL


def test_evaluate_requirement_missing_when_skill_absent(client, profile, db_session):
    ctx = get_relevant_career_data(db_session, profile["id"])
    req = JobRequirement(
        job_id=0, requirement_text="Kubernetes", category=RequirementCategory.TECHNICAL_SKILL,
        importance=RequirementImportance.HIGH, required=True, skill_name="Kubernetes",
    )
    result = evaluate_requirement(req, ctx)
    assert result.status == MatchStatus.MISSING


def test_evaluate_requirement_unknown_for_work_authorization(client, profile, db_session):
    """The Step 1 profile schema has no work-authorization field at all --
    this must never be guessed at, so it is always 'unknown', never
    'matched' or 'missing'."""
    ctx = get_relevant_career_data(db_session, profile["id"])
    req = JobRequirement(
        job_id=0, requirement_text="Must be authorized to work in the US",
        category=RequirementCategory.WORK_AUTHORIZATION, importance=RequirementImportance.CRITICAL, required=True,
    )
    result = evaluate_requirement(req, ctx)
    assert result.status == MatchStatus.UNKNOWN


def test_evaluate_requirement_unknown_never_becomes_matched(client, profile, db_session):
    ctx = get_relevant_career_data(db_session, profile["id"])
    req = JobRequirement(
        job_id=0, requirement_text="Fluent in French", category=RequirementCategory.LANGUAGE,
        importance=RequirementImportance.LOW, required=False,
    )
    result = evaluate_requirement(req, ctx)
    assert result.status == MatchStatus.UNKNOWN


# --- 13, 15: score calculation / recommendation calculation -----------------


def test_score_to_recommendation_thresholds():
    t = DEFAULT_RECOMMENDATION_THRESHOLDS
    assert score_to_recommendation(90, t) == Recommendation.APPLY
    assert score_to_recommendation(75, t) == Recommendation.APPLY
    assert score_to_recommendation(74, t) == Recommendation.MAYBE
    assert score_to_recommendation(60, t) == Recommendation.MAYBE
    assert score_to_recommendation(59, t) == Recommendation.SKIP
    assert score_to_recommendation(0, t) == Recommendation.SKIP


def test_compute_match_high_score_when_required_skills_verified(client, profile, db_session):
    client.post("/skills", json={"profile_id": profile["id"], "name": "Python", "category": "Programming", "verified": True})
    client.post("/skills", json={"profile_id": profile["id"], "name": "PyTorch", "category": "ML/DL", "verified": True})

    job = _make_job_with_requirements(db_session, [
        dict(requirement_text="Python", category=RequirementCategory.TECHNICAL_SKILL,
             importance=RequirementImportance.HIGH, required=True, skill_name="Python"),
        dict(requirement_text="PyTorch", category=RequirementCategory.TECHNICAL_SKILL,
             importance=RequirementImportance.HIGH, required=True, skill_name="PyTorch"),
    ])

    match = compute_match(db_session, job, use_ai_explanation=False)
    assert match.overall_score > 0
    assert match.recommendation in (Recommendation.APPLY, Recommendation.MAYBE)
    assert any("Python" in s for s in match.strengths)


def test_compute_match_low_score_when_required_skill_missing(db_session, client, profile):
    job = _make_job_with_requirements(db_session, [
        dict(requirement_text="Kubernetes", category=RequirementCategory.TECHNICAL_SKILL,
             importance=RequirementImportance.HIGH, required=True, skill_name="Kubernetes"),
    ])
    match = compute_match(db_session, job, use_ai_explanation=False)
    assert any("Kubernetes" in w for w in match.weaknesses)


def test_compute_match_requires_extracted_requirements(db_session):
    job = Job(title="X", company="Y", description="d")
    db_session.add(job)
    db_session.commit()
    with pytest.raises(MatchInputError):
        compute_match(db_session, job, use_ai_explanation=False)


# --- 14: critical requirement override ---------------------------------------


def test_critical_missing_requirement_forces_skip_even_with_high_score(client, profile, db_session):
    client.post("/skills", json={"profile_id": profile["id"], "name": "Python", "category": "Programming", "verified": True})

    job = _make_job_with_requirements(db_session, [
        dict(requirement_text="Python", category=RequirementCategory.TECHNICAL_SKILL,
             importance=RequirementImportance.HIGH, required=True, skill_name="Python"),
        dict(requirement_text="Active TS/SCI security clearance required", category=RequirementCategory.CERTIFICATION,
             importance=RequirementImportance.CRITICAL, required=True),
    ])

    match = compute_match(db_session, job, use_ai_explanation=False)
    assert match.critical_gaps
    assert match.recommendation == Recommendation.SKIP


# --- API-level match endpoints (also covers #18: works without an API key) --


def test_match_endpoint_works_without_api_key_once_already_analyzed(client, profile, db_session):
    client.post("/skills", json={"profile_id": profile["id"], "name": "Python", "category": "Programming", "verified": True})
    job = _make_job_with_requirements(db_session, [
        dict(requirement_text="Python", category=RequirementCategory.TECHNICAL_SKILL,
             importance=RequirementImportance.HIGH, required=True, skill_name="Python"),
    ])

    resp = client.post(f"/jobs/{job.id}/match")
    assert resp.status_code == 200
    body = resp.json()
    assert 0 <= body["score"] <= 100
    assert body["recommendation"] in ("apply", "maybe", "skip")
    assert body["summary"]

    resp2 = client.get(f"/jobs/{job.id}/match")
    assert resp2.status_code == 200
    assert resp2.json()["score"] == body["score"]


def test_get_match_404_before_matching(client):
    job_id = client.post("/jobs", json={"description": "Some job description here."}).json()["job"]["id"]
    resp = client.get(f"/jobs/{job_id}/match")
    assert resp.status_code == 404
