import pytest

from app.ai.client import AIConfigurationError
from app.ai.structured_outputs import CoverLetterOutput
from app.models.enums import EntityType
from app.services import cover_letter_service as svc


REQUIREMENTS = [
    dict(requirement_text="PyTorch", category="technical_skill", importance="high", required=True, skill_name="PyTorch"),
    dict(requirement_text="Computer Vision", category="technical_skill", importance="high", required=True, skill_name="Computer Vision"),
]


def _good_output(word_count=300):
    body = "I am writing to express interest in this role. " * (word_count // 9)
    return CoverLetterOutput(
        opening="I am writing to express interest in this role.",
        role_alignment="This role focuses on computer vision, which matches my experience.",
        experience_alignment="At Acme AI I developed deep learning models for medical image segmentation using PyTorch.",
        company_alignment="The role's emphasis on computer vision aligns with my project work.",
        closing="Thank you for your consideration.",
        full_text=body,
    )


# --- 1: cover letter generation / 6: evidence traceability -----------------


def test_generate_cover_letter_creates_validated_version(client, rich_profile, db_session, make_analyzed_job, make_approved_cv, mocker, fake_ollama_client):
    job = make_analyzed_job(requirements=REQUIREMENTS)
    cv = make_approved_cv(job.id, rich_profile["profile"]["id"])

    output = CoverLetterOutput(
        opening="I am writing to express interest in the Machine Learning Engineer role.",
        role_alignment="This role's focus on computer vision aligns with my project work.",
        experience_alignment="At Acme AI, I developed deep learning models for medical image segmentation using PyTorch.",
        company_alignment="The role's emphasis on computer vision matches my background.",
        closing="Thank you for considering my application.",
        full_text=(
            "I am writing to express interest in the Machine Learning Engineer role. "
            "At Acme AI, I developed deep learning models for medical image segmentation using PyTorch, "
            "and on the Hirschsprung Disease Segmentation project I worked extensively with computer vision. "
            "This role's focus on computer vision aligns closely with that experience. "
            "Thank you for considering my application."
        ),
    )
    mocker.patch("app.services.cover_letter_service.get_ollama_client", return_value=fake_ollama_client(output))

    cl = svc.generate_cover_letter(db_session, job, cv)

    assert cl.version_number == 1
    assert cl.status.value in ("validated", "draft")  # word count may land outside target in this short fixture
    assert cl.word_count > 0
    assert {"source_type": EntityType.EXPERIENCE.value, "source_id": rich_profile["experience"]["id"]} in cl.source_evidence
    assert {"source_type": EntityType.PROJECT.value, "source_id": rich_profile["project"]["id"]} in cl.source_evidence


def test_generate_cover_letter_requires_approved_cv(client, rich_profile, db_session, make_analyzed_job):
    from app.models.cv_version import CVVersion
    from app.models.enums import CVStatus

    job = make_analyzed_job(requirements=REQUIREMENTS)
    cv = CVVersion(
        job_id=job.id, profile_id=rich_profile["profile"]["id"],
        version_name="Draft CV", version_number=1, status=CVStatus.DRAFT,
    )
    db_session.add(cv)
    db_session.commit()

    with pytest.raises(svc.CoverLetterInputError):
        svc.generate_cover_letter(db_session, job, cv)


# --- 2, 3, 4, 5: validation / unsupported claim / technology / metric ------


def test_unsupported_skill_in_letter_causes_rejection(client, rich_profile, db_session, make_analyzed_job, make_approved_cv, mocker, fake_ollama_client):
    job = make_analyzed_job(requirements=[
        dict(requirement_text="AWS", category="technical_skill", importance="medium", required=False, skill_name="AWS"),
    ])
    cv = make_approved_cv(job.id, rich_profile["profile"]["id"])

    bad_output = CoverLetterOutput(
        opening="x", role_alignment="x", experience_alignment="x", company_alignment="x", closing="x",
        full_text="I have extensive experience with AWS cloud infrastructure and deployment.",
    )
    mocker.patch("app.services.cover_letter_service.get_ollama_client", return_value=fake_ollama_client(bad_output, bad_output))

    cl = svc.generate_cover_letter(db_session, job, cv)

    assert cl.status.value == "rejected"
    assert any("AWS" in w for w in cl.warnings)


def test_unsupported_metric_in_letter_causes_rejection(client, rich_profile, db_session, make_analyzed_job, make_approved_cv, mocker, fake_ollama_client):
    job = make_analyzed_job(requirements=REQUIREMENTS)
    cv = make_approved_cv(job.id, rich_profile["profile"]["id"])

    bad_output = CoverLetterOutput(
        opening="x", role_alignment="x", experience_alignment="x", company_alignment="x", closing="x",
        full_text="I improved model accuracy by 47% using PyTorch in my previous role.",
    )
    mocker.patch("app.services.cover_letter_service.get_ollama_client", return_value=fake_ollama_client(bad_output, bad_output))

    cl = svc.generate_cover_letter(db_session, job, cv)

    assert cl.status.value == "rejected"
    assert any("47" in w for w in cl.warnings)


def test_letter_with_only_supported_claims_is_not_rejected(client, rich_profile, db_session, make_analyzed_job, make_approved_cv, mocker, fake_ollama_client):
    job = make_analyzed_job(requirements=REQUIREMENTS)
    cv = make_approved_cv(job.id, rich_profile["profile"]["id"])

    good = _good_output()
    mocker.patch("app.services.cover_letter_service.get_ollama_client", return_value=fake_ollama_client(good))

    cl = svc.generate_cover_letter(db_session, job, cv)
    assert cl.status.value != "rejected"


# --- user instructions cannot smuggle in unsupported claims (spec section 36) -


def test_instruction_to_add_unsupported_skill_is_rejected_before_generation(client, rich_profile, db_session, make_analyzed_job, make_approved_cv, mocker, fake_ollama_client):
    job = make_analyzed_job(requirements=REQUIREMENTS)
    cv = make_approved_cv(job.id, rich_profile["profile"]["id"])

    ollama_client = mocker.patch("app.services.cover_letter_service.get_ollama_client")

    with pytest.raises(svc.CoverLetterInputError, match="AWS is not present in the verified Career Profile"):
        svc.generate_cover_letter(db_session, job, cv, instructions="Please add AWS to my cover letter.")

    ollama_client.assert_not_called()


# --- style/length validation -------------------------------------------


def test_invalid_style_is_rejected(client, rich_profile, db_session, make_analyzed_job, make_approved_cv):
    job = make_analyzed_job(requirements=REQUIREMENTS)
    cv = make_approved_cv(job.id, rich_profile["profile"]["id"])
    with pytest.raises(svc.CoverLetterStyleError):
        svc.generate_cover_letter(db_session, job, cv, style="sarcastic")


# --- 18: versioning / 19: regeneration --------------------------------------


def test_regenerating_creates_new_version_without_deleting_old(client, rich_profile, db_session, make_analyzed_job, make_approved_cv, mocker, fake_ollama_client):
    job = make_analyzed_job(requirements=REQUIREMENTS)
    cv = make_approved_cv(job.id, rich_profile["profile"]["id"])
    good = _good_output()

    mocker.patch("app.services.cover_letter_service.get_ollama_client", return_value=fake_ollama_client(good))
    cl1 = svc.generate_cover_letter(db_session, job, cv)

    mocker.patch("app.services.cover_letter_service.get_ollama_client", return_value=fake_ollama_client(good))
    cl2 = svc.generate_cover_letter(db_session, job, cv)

    assert cl1.id != cl2.id
    assert cl1.version_number == 1
    assert cl2.version_number == 2

    from app.models.cover_letter import CoverLetter
    still_there = db_session.get(CoverLetter, cl1.id)
    assert still_there is not None


# --- 20: approval workflow / API endpoints ----------------------------------


def test_cover_letter_approval_workflow_via_api(client, rich_profile, db_session, make_analyzed_job, make_approved_cv, mocker, fake_ollama_client):
    job = make_analyzed_job(requirements=REQUIREMENTS)
    cv = make_approved_cv(job.id, rich_profile["profile"]["id"])
    good = _good_output()
    mocker.patch("app.services.cover_letter_service.get_ollama_client", return_value=fake_ollama_client(good))

    resp = client.post(f"/jobs/{job.id}/cover-letter/generate")
    assert resp.status_code == 201
    cl_id = resp.json()["id"]

    fetched = client.get(f"/cover-letters/{cl_id}")
    assert fetched.status_code == 200

    approve = client.patch(f"/cover-letters/{cl_id}/status", json={"status": "approved"})
    assert approve.status_code == 200
    assert approve.json()["status"] == "approved"

    versions = client.get(f"/cover-letters/{cl_id}/versions")
    assert versions.status_code == 200
    assert versions.json()["total"] == 1

    txt = client.get(f"/cover-letters/{cl_id}/download")
    assert txt.status_code == 200
    assert len(txt.text) > 0


# --- 22: missing Ollama handling --------------------------------------------


def test_generate_without_ollama_model_configured_raises(client, rich_profile, db_session, make_analyzed_job, make_approved_cv):
    job = make_analyzed_job(requirements=REQUIREMENTS)
    cv = make_approved_cv(job.id, rich_profile["profile"]["id"])
    with pytest.raises(AIConfigurationError):
        svc.generate_cover_letter(db_session, job, cv)


def test_generate_endpoint_without_ollama_returns_503(client, rich_profile, db_session, make_analyzed_job, make_approved_cv):
    job = make_analyzed_job(requirements=REQUIREMENTS)
    make_approved_cv(job.id, rich_profile["profile"]["id"])
    resp = client.post(f"/jobs/{job.id}/cover-letter/generate")
    assert resp.status_code == 503
    assert "OLLAMA_MODEL" in resp.json()["detail"]
