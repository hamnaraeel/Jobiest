from unittest.mock import MagicMock

import requests

from app.services.job_ingestion_service import find_possible_duplicate_by_identity, ingest_job
from app.services.job_parser import clean_html_to_text, fetch_job_url, normalize_url

SAMPLE_DESCRIPTION = """Machine Learning Engineer - Example Company

We are looking for a Machine Learning Engineer to join our computer vision team.

Requirements:
- 2+ years of experience with Python
- Strong experience with PyTorch

Preferred:
- Experience with AWS is a plus
"""

SAMPLE_HTML = """
<html>
<head><script>trackPageView();</script><style>.x{color:red}</style></head>
<body>
<nav>Home | Jobs | About</nav>
<div class="cookie-banner">We use cookies. Accept?</div>
<main>
<h1>Machine Learning Engineer</h1>
<p>Example Company is looking for an ML Engineer with strong Python and PyTorch experience.</p>
<p>Responsibilities include building and deploying computer vision models in production.</p>
<p>Requirements: 2+ years Python, PyTorch, computer vision experience preferred.</p>
</main>
<footer>Copyright 2026 Example Company. All rights reserved.</footer>
</body>
</html>
"""


# --- 1 & 2: creating a job / creating a job from a description ------------


def test_create_job_from_description(client):
    resp = client.post("/jobs", json={"description": SAMPLE_DESCRIPTION})
    assert resp.status_code == 201
    body = resp.json()
    assert body["created"] is True
    assert body["job"]["description"].startswith("Machine Learning Engineer")
    assert body["job"]["status"] == "discovered"
    assert body["fetch_notice"] is None


def test_create_job_requires_url_or_description(client):
    resp = client.post("/jobs", json={})
    assert resp.status_code == 422


# --- 3: URL ingestion (mocked HTTP) ----------------------------------------


def test_create_job_from_url_success(client, mocker):
    fake_response = MagicMock()
    fake_response.status_code = 200
    fake_response.headers = {"content-type": "text/html; charset=utf-8"}
    fake_response.text = SAMPLE_HTML
    mocker.patch("app.services.job_parser.requests.get", return_value=fake_response)

    resp = client.post("/jobs", json={"url": "https://example.com/jobs/123"})
    assert resp.status_code == 201
    body = resp.json()
    assert body["fetch_notice"] is None
    assert "Machine Learning Engineer" in body["job"]["description"]
    assert "cookie" not in body["job"]["description"].lower()
    assert "copyright" not in body["job"]["description"].lower()


def test_create_job_from_unreachable_url_requires_manual_input(client, mocker):
    mocker.patch("app.services.job_parser.requests.get", side_effect=requests.ConnectionError("boom"))

    resp = client.post("/jobs", json={"url": "https://example.com/jobs/999"})
    assert resp.status_code == 201
    body = resp.json()
    assert body["fetch_notice"] == {
        "status": "manual_input_required",
        "message": "Unable to extract job description automatically. Please paste the job description.",
    }
    assert body["job"]["description"] is None


# --- 4: invalid URL ---------------------------------------------------------


def test_fetch_job_url_invalid_url_handled_gracefully():
    result = fetch_job_url("not a valid url at all")
    assert result.ok is False
    assert result.error


def test_create_job_with_garbage_url_does_not_crash(client):
    resp = client.post("/jobs", json={"url": "not a valid url"})
    assert resp.status_code == 201
    assert resp.json()["fetch_notice"]["status"] == "manual_input_required"


# --- 5: cleaning HTML --------------------------------------------------------


def test_clean_html_to_text_strips_noise():
    cleaned = clean_html_to_text(SAMPLE_HTML)
    assert cleaned is not None
    assert "Machine Learning Engineer" in cleaned
    assert "trackPageView" not in cleaned
    assert "cookies" not in cleaned.lower()
    assert "Home | Jobs | About" not in cleaned
    assert "Copyright" not in cleaned


def test_clean_html_to_text_returns_none_for_thin_js_shell():
    shell = "<html><body><div id='root'></div><script>renderApp()</script></body></html>"
    assert clean_html_to_text(shell) is None


def test_normalize_url_strips_tracking_and_trailing_slash():
    a = normalize_url("https://WWW.Example.com/jobs/123/?utm_source=linkedin&ref=abc")
    b = normalize_url("https://example.com/jobs/123")
    assert a == b


# --- 16: duplicate job detection --------------------------------------------


def test_ingest_job_dedups_on_same_url(db_session, mocker):
    fake_response = MagicMock()
    fake_response.status_code = 200
    fake_response.headers = {"content-type": "text/html"}
    fake_response.text = SAMPLE_HTML
    get_mock = mocker.patch("app.services.job_parser.requests.get", return_value=fake_response)

    first = ingest_job(db_session, "https://example.com/jobs/1?utm_source=x", None)
    second = ingest_job(db_session, "https://example.com/jobs/1", None)

    assert first.created is True
    assert second.created is False
    assert first.job.id == second.job.id
    assert get_mock.call_count == 1


def test_ingest_job_dedups_on_identical_description(db_session):
    first = ingest_job(db_session, None, SAMPLE_DESCRIPTION)
    second = ingest_job(db_session, None, SAMPLE_DESCRIPTION)

    assert first.created is True
    assert second.created is False
    assert first.job.id == second.job.id


def test_find_possible_duplicate_by_identity(db_session):
    first = ingest_job(db_session, None, "Some description A").job
    first.title, first.company, first.location = "ML Engineer", "Acme Corp", "Remote"
    second = ingest_job(db_session, None, "Some description B, totally different text here").job
    second.title, second.company, second.location = "ml engineer", "ACME CORP", "remote"
    db_session.commit()

    duplicate = find_possible_duplicate_by_identity(db_session, second)
    assert duplicate is not None
    assert duplicate.id == first.id


# --- 17: API endpoints -------------------------------------------------------


def test_get_job_404(client):
    resp = client.get("/jobs/999999")
    assert resp.status_code == 404


def test_list_jobs_pagination_and_filters(client):
    client.post("/jobs", json={"description": "Job one about Python and Django. Company: Acme"})
    client.post("/jobs", json={"description": "Job two about Rust and Go. Company: Globex"})

    resp = client.get("/jobs")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 2
    assert len(body["items"]) == 2

    resp = client.get("/jobs", params={"search": "Rust"})
    assert resp.json()["total"] == 1

    resp = client.get("/jobs", params={"limit": 1, "offset": 0})
    assert len(resp.json()["items"]) == 1


def test_get_job_requirements_empty_before_analysis(client):
    job_id = client.post("/jobs", json={"description": SAMPLE_DESCRIPTION}).json()["job"]["id"]
    resp = client.get(f"/jobs/{job_id}/requirements")
    assert resp.status_code == 200
    assert resp.json() == []


# --- 18: missing OpenAI API key handling ------------------------------------


def test_analyze_without_api_key_returns_clear_error(client):
    job_id = client.post("/jobs", json={"description": SAMPLE_DESCRIPTION}).json()["job"]["id"]
    resp = client.post(f"/jobs/{job_id}/analyze")
    assert resp.status_code == 503
    assert "OPENAI_API_KEY" in resp.json()["detail"]


def test_match_without_analysis_or_api_key_returns_clear_error(client):
    job_id = client.post("/jobs", json={"description": SAMPLE_DESCRIPTION}).json()["job"]["id"]
    resp = client.post(f"/jobs/{job_id}/match")
    assert resp.status_code == 503
