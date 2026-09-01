"""The "Profile Parser": resume upload -> text extraction -> AI structured
extraction -> human review -> confirm (writes unverified profile rows) or
reject (discards). AI calls are mocked throughout (matching
test_cv_customization.py's pattern) -- the extraction logic itself
(OpenAI's own structured-output quality) isn't this project's concern to
test; what matters here is that nothing gets written without an explicit
confirm, and everything written lands unverified."""

from unittest.mock import MagicMock

import pytest

from app.agent import tool_router
from app.ai.client import AIConfigurationError
from app.ai.resume_parse_outputs import (
    ParsedExperience,
    ParsedExperienceBullet,
    ParsedProject,
    ParsedSkill,
    ResumeParseOutput,
)
from app.models.enums import ResumeImportStatus
from app.models.resume_import import ResumeImport
from app.services import resume_import_service as svc


def _fake_openai_client(parsed: ResumeParseOutput):
    client = MagicMock()
    message = MagicMock()
    message.parsed = parsed
    choice = MagicMock()
    choice.message = message
    completion = MagicMock()
    completion.choices = [choice]
    client.chat.completions.parse.return_value = completion
    return client


def _sample_parsed(**overrides) -> ResumeParseOutput:
    defaults = dict(
        full_name="Jordan Rivera", professional_title="Machine Learning Engineer", email="jordan@example.com",
        skills=[ParsedSkill(name="PyTorch", category="ML/DL", proficiency="advanced", years_used=4)],
        experience=[ParsedExperience(
            company="Acme AI", role="ML Engineer", employment_type="full_time", start_date="2022-01-01",
            currently_working=True, bullets=[ParsedExperienceBullet(bullet="Built segmentation models.", skills=["PyTorch"])],
        )],
    )
    defaults.update(overrides)
    return ResumeParseOutput(**defaults)


# --- extract_text -----------------------------------------------------


def test_extract_text_accepts_plain_text():
    text = svc.extract_text("resume.txt", b"A" * 200)
    assert text == "A" * 200


def test_extract_text_rejects_unsupported_extension():
    with pytest.raises(svc.ResumeImportError):
        svc.extract_text("resume.docx", b"A" * 200)


def test_extract_text_rejects_too_short_content():
    with pytest.raises(svc.ResumeImportError):
        svc.extract_text("resume.txt", b"too short")


# --- parse_resume (mocked AI boundary) -------------------------------


def test_parse_resume_creates_pending_review_import(db_session, mocker):
    mocker.patch("app.services.resume_import_service.get_ai_client", return_value=_fake_openai_client(_sample_parsed()))
    resume_import = svc.parse_resume(db_session, "resume.txt", b"A career summary. " * 20)
    assert resume_import.status == ResumeImportStatus.PENDING_REVIEW
    assert resume_import.parsed_data["full_name"] == "Jordan Rivera"
    assert resume_import.warnings == []


def test_parse_resume_warns_when_name_or_email_missing(db_session, mocker):
    incomplete = _sample_parsed(full_name=None, email=None)
    mocker.patch("app.services.resume_import_service.get_ai_client", return_value=_fake_openai_client(incomplete))
    resume_import = svc.parse_resume(db_session, "resume.txt", b"A career summary. " * 20)
    assert any("email" in w.lower() for w in resume_import.warnings)
    assert any("name" in w.lower() for w in resume_import.warnings)


def test_parse_resume_surfaces_missing_api_key_clearly(db_session, mocker):
    mocker.patch("app.services.resume_import_service.get_ai_client", side_effect=AIConfigurationError("no key"))
    with pytest.raises(AIConfigurationError):
        svc.parse_resume(db_session, "resume.txt", b"A career summary. " * 20)


def test_parse_resume_rejects_bad_file_before_ever_calling_ai(db_session, mocker):
    ai_mock = mocker.patch("app.services.resume_import_service.get_ai_client")
    with pytest.raises(svc.ResumeImportError):
        svc.parse_resume(db_session, "resume.docx", b"A" * 200)
    ai_mock.assert_not_called()


# --- confirm_import / reject_import ------------------------------------


def test_confirm_import_creates_new_profile_all_unverified(db_session, mocker):
    mocker.patch("app.services.resume_import_service.get_ai_client", return_value=_fake_openai_client(_sample_parsed()))
    resume_import = svc.parse_resume(db_session, "resume.txt", b"A career summary. " * 20)

    profile = svc.confirm_import(db_session, resume_import)
    assert profile.full_name == "Jordan Rivera"
    assert len(profile.skills) == 1
    assert profile.skills[0].verified is False
    assert len(profile.experiences) == 1
    assert profile.experiences[0].verified is False
    assert profile.experiences[0].bullets[0].verified is False

    db_session.refresh(resume_import)
    assert resume_import.status == ResumeImportStatus.CONFIRMED
    assert resume_import.profile_id == profile.id
    assert resume_import.confirmed_at is not None


def test_confirm_import_attaches_to_existing_profile(db_session, mocker, profile):
    mocker.patch("app.services.resume_import_service.get_ai_client", return_value=_fake_openai_client(_sample_parsed()))
    resume_import = svc.parse_resume(db_session, "resume.txt", b"A career summary. " * 20)

    result = svc.confirm_import(db_session, resume_import)
    assert result.id == profile["id"]
    assert len(result.skills) == 1


def test_confirm_import_without_profile_or_contact_info_raises(db_session, mocker):
    incomplete = _sample_parsed(full_name=None, email=None)
    mocker.patch("app.services.resume_import_service.get_ai_client", return_value=_fake_openai_client(incomplete))
    resume_import = svc.parse_resume(db_session, "resume.txt", b"A career summary. " * 20)

    with pytest.raises(svc.ResumeImportError):
        svc.confirm_import(db_session, resume_import)


def test_confirm_already_confirmed_import_raises(db_session, mocker):
    mocker.patch("app.services.resume_import_service.get_ai_client", return_value=_fake_openai_client(_sample_parsed()))
    resume_import = svc.parse_resume(db_session, "resume.txt", b"A career summary. " * 20)
    svc.confirm_import(db_session, resume_import)
    with pytest.raises(svc.ResumeImportError):
        svc.confirm_import(db_session, resume_import)


def test_reject_import_discards_without_writing_anything(db_session, mocker, profile):
    mocker.patch("app.services.resume_import_service.get_ai_client", return_value=_fake_openai_client(_sample_parsed()))
    resume_import = svc.parse_resume(db_session, "resume.txt", b"A career summary. " * 20)

    svc.reject_import(db_session, resume_import)
    db_session.refresh(resume_import)
    assert resume_import.status == ResumeImportStatus.REJECTED

    from app.models.skill import Skill
    assert db_session.query(Skill).count() == 0


# --- API endpoints -------------------------------------------------------


def test_api_upload_rejects_unsupported_file_type(client):
    resp = client.post("/profile/resume/upload", files={"file": ("resume.docx", b"A" * 200, "application/octet-stream")})
    assert resp.status_code == 422


def test_api_upload_returns_503_without_openai_key(client, mocker):
    mocker.patch("app.services.resume_import_service.get_ai_client", side_effect=AIConfigurationError("no key"))
    resp = client.post("/profile/resume/upload", files={"file": ("resume.txt", b"A career summary. " * 20, "text/plain")})
    assert resp.status_code == 503


def test_api_upload_list_get_confirm_flow(client, mocker):
    mocker.patch("app.services.resume_import_service.get_ai_client", return_value=_fake_openai_client(_sample_parsed()))
    upload = client.post("/profile/resume/upload", files={"file": ("resume.txt", b"A career summary. " * 20, "text/plain")})
    assert upload.status_code == 201
    import_id = upload.json()["id"]

    listed = client.get("/profile/resume/imports")
    assert listed.json()["total"] == 1

    fetched = client.get(f"/profile/resume/imports/{import_id}")
    assert fetched.json()["status"] == "pending_review"

    confirmed = client.post(f"/profile/resume/imports/{import_id}/confirm", json={})
    assert confirmed.status_code == 200
    assert confirmed.json()["full_name"] == "Jordan Rivera"


def test_api_get_missing_import_404s(client):
    assert client.get("/profile/resume/imports/999999").status_code == 404


def test_api_reject_flow(client, mocker):
    mocker.patch("app.services.resume_import_service.get_ai_client", return_value=_fake_openai_client(_sample_parsed()))
    upload = client.post("/profile/resume/upload", files={"file": ("resume.txt", b"A career summary. " * 20, "text/plain")})
    import_id = upload.json()["id"]

    rejected = client.post(f"/profile/resume/imports/{import_id}/reject")
    assert rejected.json()["status"] == "rejected"

    assert client.post(f"/profile/resume/imports/{import_id}/confirm", json={}).status_code == 422


# --- Agent tools ---------------------------------------------------------


@pytest.mark.asyncio
async def test_agent_list_resume_imports_tool(db_session, mocker):
    mocker.patch("app.services.resume_import_service.get_ai_client", return_value=_fake_openai_client(_sample_parsed()))
    svc.parse_resume(db_session, "resume.txt", b"A career summary. " * 20)

    envelope, _ = await tool_router.invoke(db_session, "career.list_resume_imports", {})
    assert envelope["success"] is True
    assert envelope["data"]["total"] == 1


def test_agent_confirm_resume_import_always_requires_approval():
    from app.agent.tool_registry import get_tool
    spec = get_tool("career.confirm_resume_import")
    assert spec.requires_approval is True
    assert spec.risk.value in ("medium", "high")


@pytest.mark.asyncio
async def test_agent_confirm_resume_import_tool_writes_unverified_rows(db_session, mocker):
    mocker.patch("app.services.resume_import_service.get_ai_client", return_value=_fake_openai_client(_sample_parsed()))
    resume_import = svc.parse_resume(db_session, "resume.txt", b"A career summary. " * 20)

    envelope, _ = await tool_router.invoke(db_session, "career.confirm_resume_import", {"resume_import_id": resume_import.id})
    assert envelope["success"] is True
    assert envelope["data"]["profile"]["full_name"] == "Jordan Rivera"

    from app.models.skill import Skill
    skill = db_session.query(Skill).one()
    assert skill.verified is False


# --- project link sanitizing ------------------------------------------------
#
# Resume import is the only project write path that does not go through an
# HttpUrl-typed schema field, and a resume's link is usually a hyperlink
# whose visible text is a word rather than its href. Storing that word made
# GET /projects fail to serialize *every* project, so this is guarded at the
# write and at the endpoint.


def test_import_drops_anchor_text_masquerading_as_a_project_link(db_session, mocker):
    parsed = _sample_parsed(projects=[
        ParsedProject(name="Segmentation Study", github_url="GitHub", demo_url="Live Demo"),
        ParsedProject(name="CloudETL", github_url="github.com/jordan/cloudetl"),
    ])
    mocker.patch("app.services.resume_import_service.get_ai_client", return_value=_fake_openai_client(parsed))
    resume_import = svc.parse_resume(db_session, "resume.txt", b"A career summary. " * 20)

    profile = svc.confirm_import(db_session, resume_import)
    by_name = {p.name: p for p in profile.projects}

    # Prose is not a link -- dropping it beats rendering one that goes nowhere.
    assert by_name["Segmentation Study"].github_url is None
    assert by_name["Segmentation Study"].demo_url is None
    # A real link missing only its scheme is still a real link.
    assert by_name["CloudETL"].github_url == "https://github.com/jordan/cloudetl"


def test_projects_endpoint_serializes_a_project_with_no_links(client, profile):
    """The regression itself: ProjectRead types these columns as HttpUrl, so
    a single unparseable value used to 500 the whole list endpoint."""

    created = client.post("/projects", json={"profile_id": profile["id"], "name": "No Links"})
    assert created.status_code == 201, created.text

    listed = client.get("/projects")
    assert listed.status_code == 200, listed.text
    assert any(p["name"] == "No Links" for p in listed.json())
