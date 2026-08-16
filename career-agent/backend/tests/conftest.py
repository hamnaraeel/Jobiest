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
