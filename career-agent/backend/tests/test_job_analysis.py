from unittest.mock import MagicMock

import pytest

from app.ai.client import AIConfigurationError
from app.ai.structured_outputs import JobAnalysisResult
from app.models.job import Job
from app.models.enums import JobStatus, RequirementCategory
from app.services.job_analysis_service import AIResponseError, AnalysisInputError, analyze_job, call_job_analysis

SAMPLE_ANALYSIS = JobAnalysisResult(
    job_title="Machine Learning Engineer",
    company="Example Company",
    location="Islamabad, Pakistan",
    job_summary="Machine Learning Engineer responsible for building and deploying computer vision models.",
    required_skills=["Python", "PyTorch", "Computer Vision"],
    preferred_skills=["AWS", "Docker"],
    required_experience=["2+ years of experience in machine learning"],
    preferred_experience=["Experience with production ML systems is a plus"],
    education_requirements=["Bachelor's degree in Computer Science or related field"],
    responsibilities=["Develop and deploy deep learning models for computer vision tasks"],
    certifications=[],
    location_requirements=["Islamabad, Pakistan (remote friendly)"],
    work_authorization_requirements=["Must be authorized to work in Pakistan"],
    keywords=["Python", "PyTorch", "Computer Vision", "Deep Learning", "AWS", "Docker"],
)


def _fake_client(parsed):
    client = MagicMock()
    message = MagicMock()
    message.parsed = parsed
    choice = MagicMock()
    choice.message = message
    completion = MagicMock()
    completion.choices = [choice]
    client.chat.completions.parse.return_value = completion
    return client


# --- call_job_analysis: mocked OpenAI response handling ---------------------


def test_call_job_analysis_returns_parsed_result():
    client = _fake_client(SAMPLE_ANALYSIS)
    result = call_job_analysis(client, "gpt-4o-mini", "some job description")
    assert result.job_title == "Machine Learning Engineer"
    assert result.required_skills == ["Python", "PyTorch", "Computer Vision"]


def test_call_job_analysis_raises_on_openai_error():
    client = MagicMock()
    client.chat.completions.parse.side_effect = RuntimeError("connection reset")
    with pytest.raises(AIResponseError):
        call_job_analysis(client, "gpt-4o-mini", "some job description")


def test_call_job_analysis_raises_when_no_parsed_output():
    client = MagicMock()
    message = MagicMock()
    message.parsed = None
    message.refusal = "content policy"
    choice = MagicMock()
    choice.message = message
    completion = MagicMock()
    completion.choices = [choice]
    client.chat.completions.parse.return_value = completion

    with pytest.raises(AIResponseError):
        call_job_analysis(client, "gpt-4o-mini", "some job description")


# --- 6: extracting requirements / 7: required vs preferred ------------------


def test_analyze_job_extracts_requirements_and_backfills_job_fields(db_session, mocker):
    mocker.patch("app.services.job_analysis_service.get_ai_client", return_value=_fake_client(SAMPLE_ANALYSIS))

    job = Job(description="raw description text")
    db_session.add(job)
    db_session.commit()

    updated = analyze_job(db_session, job)

    assert updated.title == "Machine Learning Engineer"
    assert updated.company == "Example Company"
    assert updated.status == JobStatus.ANALYZED
    assert updated.extracted_at is not None
    assert updated.summary.startswith("Machine Learning Engineer responsible")
    assert set(updated.keywords) == set(SAMPLE_ANALYSIS.keywords)

    requirements = updated.requirements
    required_skill_names = {r.skill_name for r in requirements if r.category == RequirementCategory.TECHNICAL_SKILL and r.required}
    preferred_skill_names = {r.skill_name for r in requirements if r.category == RequirementCategory.TECHNICAL_SKILL and not r.required}

    assert required_skill_names == {"Python", "PyTorch", "Computer Vision"}
    assert preferred_skill_names == {"AWS", "Docker"}

    work_auth = [r for r in requirements if r.category == RequirementCategory.WORK_AUTHORIZATION]
    assert len(work_auth) == 1
    assert work_auth[0].importance.value == "critical"


def test_preferred_skills_never_marked_required(db_session, mocker):
    mocker.patch("app.services.job_analysis_service.get_ai_client", return_value=_fake_client(SAMPLE_ANALYSIS))

    job = Job(description="raw description text")
    db_session.add(job)
    db_session.commit()
    updated = analyze_job(db_session, job)

    aws_req = next(r for r in updated.requirements if r.skill_name == "AWS")
    assert aws_req.required is False


def test_analyze_job_reanalysis_replaces_old_requirements(db_session, mocker):
    mocker.patch("app.services.job_analysis_service.get_ai_client", return_value=_fake_client(SAMPLE_ANALYSIS))

    job = Job(description="raw description text")
    db_session.add(job)
    db_session.commit()

    analyze_job(db_session, job)
    first_count = len(job.requirements)
    analyze_job(db_session, job)
    second_count = len(job.requirements)

    assert first_count == second_count > 0


def test_analyze_job_without_description_raises(db_session):
    job = Job()
    db_session.add(job)
    db_session.commit()
    with pytest.raises(AnalysisInputError):
        analyze_job(db_session, job)


def test_analyze_job_without_api_key_raises_configuration_error(db_session):
    job = Job(description="raw description text")
    db_session.add(job)
    db_session.commit()
    with pytest.raises(AIConfigurationError):
        analyze_job(db_session, job)


# --- 18: missing OpenAI API key handling (API-level, mirrored from test_jobs) -


def test_analyze_endpoint_without_api_key(client):
    job_id = client.post("/jobs", json={"description": "Some job description text here."}).json()["job"]["id"]
    resp = client.post(f"/jobs/{job_id}/analyze")
    assert resp.status_code == 503
    assert "OPENAI_API_KEY" in resp.json()["detail"]
