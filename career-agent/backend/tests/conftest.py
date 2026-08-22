import os

# Must be set before any `from app.config import get_settings` call anywhere
# in the test session, since Settings is process-wide lru_cache'd: the real
# app defaults BROWSER_HEADLESS=false (so a human user can watch/intervene),
# but the test suite launches many real Playwright browser sessions and
# must never pop visible windows during an automated run. DRY_RUN is
# already true by default -- set explicitly here so tests never depend on
# whatever a developer's local .env happens to contain.
os.environ.setdefault("BROWSER_HEADLESS", "true")
os.environ.setdefault("DRY_RUN", "true")
# Force the OpenAI code path regardless of a developer's local .env --
# several tests assert AIConfigurationError/"OPENAI_API_KEY" when no key is
# configured, which must hold even if that .env has switched AI_PROVIDER to
# groq (with a real GROQ_API_KEY) for day-to-day local use.
os.environ["AI_PROVIDER"] = "openai"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401  (registers all models on Base.metadata)
from app.config import get_settings
from app.db.base import Base
from app.db.database import get_db
from app.main import app as fastapi_app

settings = get_settings()
engine = create_engine(settings.database_url, future=True)
TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine, future=True)


@pytest.fixture(scope="session", autouse=True)
def _create_schema():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(autouse=True)
def _clean_tables():
    yield
    with engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            conn.execute(table.delete())


@pytest.fixture
def db_session():
    session = TestSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client():
    def _override_get_db():
        session = TestSessionLocal()
        try:
            yield session
        finally:
            session.close()

    fastapi_app.dependency_overrides[get_db] = _override_get_db
    with TestClient(fastapi_app) as c:
        yield c
    fastapi_app.dependency_overrides.clear()


@pytest.fixture
def profile_payload():
    return {
        "full_name": "YOUR_NAME",
        "professional_title": "Machine Learning Engineer",
        "email": "test-profile@example.com",
        "target_roles": ["Machine Learning Engineer", "AI Engineer"],
        "years_of_experience": 2,
    }


@pytest.fixture
def profile(client, profile_payload):
    resp = client.post("/profile", json=profile_payload)
    assert resp.status_code == 201
    return resp.json()


@pytest.fixture
def rich_profile(client, profile):
    """A profile with one verified skill, one experience (with a bullet),
    and one project (with a result) -- enough real, verified data for CV
    generation tests to select from and validate against."""

    skill = client.post("/skills", json={
        "profile_id": profile["id"], "name": "PyTorch", "category": "ML/DL",
        "proficiency": "advanced", "years_used": 2, "verified": True,
    }).json()

    experience = client.post("/experience", json={
        "profile_id": profile["id"], "company": "Acme AI", "role": "ML Engineer",
        "employment_type": "full_time", "start_date": "2023-01-01", "currently_working": True,
        "technologies": ["PyTorch"], "skills": ["PyTorch"], "verified": True,
        "bullets": [{
            "bullet": "Developed deep learning models for medical image segmentation using PyTorch.",
            "skills": ["PyTorch"], "verified": True,
        }],
    }).json()

    project = client.post("/projects", json={
        "profile_id": profile["id"], "name": "Hirschsprung Disease Segmentation",
        "technologies": ["PyTorch", "Computer Vision"], "skills": ["PyTorch", "Computer Vision"],
        "verified": True,
        "results": [{"description": "Improved segmentation accuracy", "metric": "+6.2% Dice score", "verified": True}],
    }).json()

    return {"profile": profile, "skill": skill, "experience": experience, "project": project}


@pytest.fixture
def make_analyzed_job(db_session):
    """Factory fixture: builds a Job with extracted_at already set (so it
    looks already analyzed) plus the given JobRequirement rows, bypassing
    the AI call -- for tests that only need to exercise matching/CV
    generation."""

    def _make(title="ML Engineer", company="Acme", requirements=()):
        from datetime import datetime, timezone

        from app.models.job import Job
        from app.models.job_requirement import JobRequirement

        job = Job(title=title, company=company, description="d", extracted_at=datetime.now(timezone.utc))
        db_session.add(job)
        db_session.flush()
        for req in requirements:
            db_session.add(JobRequirement(job_id=job.id, **req))
        db_session.commit()
        db_session.refresh(job)
        return job

    return _make


@pytest.fixture
def make_approved_cv(db_session):
    """Factory fixture: creates an approved CVVersion row directly
    (bypassing the full generation pipeline) for a given job/profile --
    Step 4's cover letter generation requires one to exist."""

    def _make(job_id: int, profile_id: int, version_number: int = 1):
        from app.models.cv_version import CVVersion
        from app.models.enums import CVStatus

        cv = CVVersion(
            job_id=job_id, profile_id=profile_id,
            version_name=f"Test CV - V{version_number}", version_number=version_number,
            template_name="ats/ml_engineer", status=CVStatus.APPROVED,
        )
        db_session.add(cv)
        db_session.commit()
        db_session.refresh(cv)
        return cv

    return _make


@pytest.fixture
def make_approved_cover_letter(db_session):
    """Factory fixture: creates an approved CoverLetter row directly
    (bypassing the Ollama generation pipeline), mirroring make_approved_cv
    -- Step 5's file_uploader/submission_guard tests need one to exist."""

    def _make(job_id: int, cv_version_id: int, profile_id: int, version_number: int = 1):
        from app.models.cover_letter import CoverLetter
        from app.models.enums import ApplicationMaterialStatus

        cl = CoverLetter(
            job_id=job_id, cv_version_id=cv_version_id, profile_id=profile_id,
            version_name=f"Test Cover Letter - V{version_number}", version_number=version_number,
            title="Test Cover Letter", content="Dear Hiring Manager, I am excited to apply.", word_count=8,
            status=ApplicationMaterialStatus.APPROVED,
        )
        db_session.add(cl)
        db_session.commit()
        db_session.refresh(cl)
        return cl

    return _make


@pytest.fixture
def dummy_pdf(tmp_path):
    """Writes a real (fake-content) PDF file to disk and returns its path
    -- lets tests set CVVersion.pdf_path/CoverLetter.pdf_path directly so
    file_uploader's lazy-compile path is skipped entirely (it only
    compiles when no PDF already exists on disk), keeping Step 5 tests
    independent of pdflatex."""

    def _make(name: str = "dummy.pdf") -> str:
        path = tmp_path / name
        path.write_bytes(b"%PDF-1.4 fake test pdf content")
        return str(path)

    return _make


@pytest.fixture
def fixture_url():
    """Returns a file:// URL for a file in tests/fixtures/ -- Step 5's
    browser tests must never touch real job sites, only these local
    fixtures (see tests/fixtures/test_application*.html)."""

    from pathlib import Path

    def _url(name: str) -> str:
        path = (Path(__file__).parent / "fixtures" / name).resolve()
        return f"file://{path}"

    return _url


@pytest.fixture
def allow_real_submit():
    """Flips settings.dry_run to False for the duration of one test, then
    restores it -- Settings is a process-wide lru_cache'd singleton, so
    mutating the cached instance's attribute (rather than re-instantiating
    it) is what actually reaches every module that already called
    get_settings(). Used only by the explicit-approval submission test;
    every other test relies on the safe DRY_RUN=true default."""

    from app.config import get_settings

    settings = get_settings()
    original = settings.dry_run
    settings.dry_run = False
    yield settings
    settings.dry_run = original


@pytest.fixture(autouse=True)
def _close_leftover_browser_sessions(client):
    """Safety net: browser_manager launches every session against the SAME
    persistent profile directory, so a session left open by one test would
    make the next test's start_session() fail to acquire the profile lock.

    Closes any leftover session through the `client` fixture's own
    /cancel endpoint call rather than awaiting browser_manager.close_session()
    directly: Starlette's TestClient runs async route handlers on its own
    dedicated event-loop thread (a "portal") that a session's Playwright
    objects are bound to, and awaiting them from a *different* event loop
    (e.g. one pytest-asyncio would manage separately for an async fixture)
    hangs forever instead of raising. Routing through `client` guarantees
    the close happens on the same loop that opened the session."""

    yield
    from app.browser import browser_manager

    for application_id in list(browser_manager._active_sessions.keys()):
        client.post(f"/applications/{application_id}/cancel")


@pytest.fixture
def fake_ollama_client():
    """Factory fixture: builds a fake OllamaClient-like object whose
    chat_structured() returns each given output in sequence -- mirrors the
    fake OpenAI client pattern used in Steps 2-3's tests, adapted to
    OllamaClient's simpler direct-return interface (no
    .choices[0].message.parsed unwrapping needed)."""

    from unittest.mock import MagicMock

    def _make(*outputs):
        client = MagicMock()
        client.chat_structured.side_effect = list(outputs)
        return client

    return _make
