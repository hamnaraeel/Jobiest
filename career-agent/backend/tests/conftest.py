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
