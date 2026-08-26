"""Step 8: job discovery. Covers each adapter's parsing (mocked HTTP,
never real network calls), the dedup-aware ingest path, orchestration
(per-source error isolation), query building from profile/goal, and the
API endpoints."""

from unittest.mock import MagicMock

import pytest
import requests

from app.discovery.adzuna import search_adzuna
from app.discovery.arbeitnow import search_arbeitnow
from app.discovery.base import DiscoveredJob, DiscoveryQuery, DiscoverySourceError
from app.discovery.greenhouse import search_greenhouse
from app.discovery.himalayas import search_himalayas
from app.discovery.lever import search_lever
from app.discovery.remoteok import search_remoteok
from app.discovery.remotive import search_remotive
from app.discovery.usajobs import search_usajobs
from app.discovery.weworkremotely import search_weworkremotely
from app.models.enums import DiscoveryTrigger, JobEmploymentType, WorkplaceType
from app.services.discovery_service import DiscoveryInputError, build_query, run_discovery
from app.services.job_ingestion_service import ingest_discovered_job


def _response(status_code=200, json_data=None):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data
    resp.text = str(json_data)
    return resp


# --- Greenhouse --------------------------------------------------------


def test_greenhouse_parses_matching_jobs(mocker):
    mocker.patch("app.discovery.greenhouse.requests.get", return_value=_response(200, {
        "jobs": [
            {
                "id": 111, "title": "Machine Learning Engineer", "company_name": "Acme",
                "absolute_url": "https://acme.com/jobs/111",
                "location": {"name": "Remote"},
                "content": "&lt;p&gt;" + "We need PyTorch skills. " * 30 + "&lt;/p&gt;",
                "first_published": "2026-08-01T00:00:00-04:00",
            },
            {"id": 222, "title": "Sales Manager", "company_name": "Acme", "absolute_url": "https://acme.com/jobs/222", "location": {}},
        ],
    }))

    query = DiscoveryQuery(keywords=["Machine Learning Engineer"], companies=["Acme"], limit_per_source=10)
    results = search_greenhouse(query)

    assert len(results) == 1
    job = results[0]
    assert job.source == "greenhouse"
    assert job.external_job_id == "111"
    assert job.title == "Machine Learning Engineer"
    assert job.company == "Acme"
    assert job.location == "Remote"
    assert "PyTorch" in (job.description or "")
    assert job.posted_date == "2026-08-01"


def test_greenhouse_skips_404_company_without_error(mocker):
    mocker.patch("app.discovery.greenhouse.requests.get", return_value=_response(404))
    query = DiscoveryQuery(companies=["NotOnGreenhouse"], limit_per_source=10)
    assert search_greenhouse(query) == []


def test_greenhouse_empty_companies_returns_empty(mocker):
    get_mock = mocker.patch("app.discovery.greenhouse.requests.get")
    assert search_greenhouse(DiscoveryQuery(companies=[])) == []
    get_mock.assert_not_called()


# --- Lever ---------------------------------------------------------------


def test_lever_parses_matching_jobs(mocker):
    mocker.patch("app.discovery.lever.requests.get", return_value=_response(200, [
        {
            "id": "abc-123", "text": "Computer Vision Engineer",
            "hostedUrl": "https://jobs.lever.co/acme/abc-123",
            "categories": {"location": "Austin, TX", "commitment": "Regular Full Time (Salary)"},
            "descriptionPlain": "Build computer vision models.",
            "workplaceType": "remote",
            "salaryRange": {"min": 120000, "max": 160000, "currency": "USD"},
            "createdAt": 1722470400000,
        },
        {"id": "xyz-999", "text": "Recruiter", "hostedUrl": "https://jobs.lever.co/acme/xyz-999", "categories": {}},
    ]))

    query = DiscoveryQuery(keywords=["Computer Vision"], companies=["Acme"], limit_per_source=10)
    results = search_lever(query)

    assert len(results) == 1
    job = results[0]
    assert job.external_job_id == "abc-123"
    assert job.employment_type == JobEmploymentType.FULL_TIME
    assert job.workplace_type == WorkplaceType.REMOTE
    assert job.salary_min == 120000
    assert job.salary_max == 160000
    assert job.salary_currency == "USD"


def test_lever_skips_404_company(mocker):
    mocker.patch("app.discovery.lever.requests.get", return_value=_response(404))
    assert search_lever(DiscoveryQuery(companies=["NotOnLever"])) == []


# --- RemoteOK --------------------------------------------------------------


def test_remoteok_skips_legal_notice_and_filters_by_keyword(mocker):
    mocker.patch("app.discovery.remoteok.requests.get", return_value=_response(200, [
        {"legal": "API terms..."},
        {
            "id": "555", "position": "Machine Learning Engineer", "company": "RemoteCo",
            "tags": ["python", "pytorch"], "url": "https://remoteok.com/remote-jobs/555",
            "description": "<p>" + "Great PyTorch role. " * 20 + "</p>",
            "location": "Worldwide", "salary_min": 100000, "salary_max": 140000, "date": "2026-08-10T00:00:00+00:00",
        },
        {"id": "556", "position": "Sales Rep", "company": "OtherCo", "tags": [], "url": "https://remoteok.com/remote-jobs/556"},
    ]))

    results = search_remoteok(DiscoveryQuery(keywords=["Machine Learning"], limit_per_source=10))
    assert len(results) == 1
    assert results[0].external_job_id == "555"
    assert results[0].posted_date == "2026-08-10"


# --- We Work Remotely -------------------------------------------------------


WWR_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
<item>
  <title>Acme: Machine Learning Engineer</title>
  <region>Anywhere in the World</region>
  <category>Full-Stack Programming</category>
  <description>&lt;p&gt;Build ML systems.&lt;/p&gt;</description>
  <pubDate>Wed, 22 Jul 2026 07:03:14 +0000</pubDate>
  <link>https://weworkremotely.com/remote-jobs/acme-ml-engineer</link>
</item>
<item>
  <title>Acme: Sales Manager</title>
  <region>Anywhere in the World</region>
  <category>Sales and Marketing</category>
  <description>&lt;p&gt;Sell things.&lt;/p&gt;</description>
  <pubDate>Wed, 22 Jul 2026 07:03:14 +0000</pubDate>
  <link>https://weworkremotely.com/remote-jobs/acme-sales-manager</link>
</item>
</channel></rss>"""


def test_weworkremotely_parses_and_splits_company_title(mocker):
    resp = MagicMock()
    resp.status_code = 200
    resp.content = WWR_RSS.encode("utf-8")
    mocker.patch("app.discovery.weworkremotely.requests.get", return_value=resp)

    results = search_weworkremotely(DiscoveryQuery(keywords=["Machine Learning"], limit_per_source=10))
    assert len(results) == 1
    job = results[0]
    assert job.company == "Acme"
    assert job.title == "Machine Learning Engineer"
    assert job.url == "https://weworkremotely.com/remote-jobs/acme-ml-engineer"
    assert job.posted_date == "2026-07-22"


# --- Adzuna ------------------------------------------------------------


def test_adzuna_requires_configuration():
    with pytest.raises(DiscoverySourceError):
        search_adzuna(DiscoveryQuery(keywords=["ML"]), app_id="", app_key="")


def test_adzuna_parses_results(mocker):
    mocker.patch("app.discovery.adzuna.requests.get", return_value=_response(200, {
        "results": [{
            "id": "999", "title": "ML Engineer", "company": {"display_name": "Acme"},
            "location": {"display_name": "Austin, TX"}, "description": "Build ML systems.",
            "redirect_url": "https://adzuna.com/jobs/999", "salary_min": 100000.0, "salary_max": 150000.0,
            "contract_time": "full_time", "created": "2026-08-01T00:00:00Z",
        }],
    }))

    results = search_adzuna(DiscoveryQuery(keywords=["ML"], limit_per_source=10), app_id="id", app_key="key", country="us")
    assert len(results) == 1
    job = results[0]
    assert job.external_job_id == "999"
    assert job.employment_type == JobEmploymentType.FULL_TIME
    assert job.salary_currency == "USD"


def test_adzuna_raises_on_auth_failure(mocker):
    mocker.patch("app.discovery.adzuna.requests.get", return_value=_response(401, {"exception": "AUTH_FAIL"}))
    with pytest.raises(DiscoverySourceError):
        search_adzuna(DiscoveryQuery(keywords=["ML"]), app_id="bad", app_key="bad")


# --- USAJobs -------------------------------------------------------------


def test_usajobs_requires_configuration():
    with pytest.raises(DiscoverySourceError):
        search_usajobs(DiscoveryQuery(keywords=["Data Scientist"]), api_key="", user_agent_email="")


def test_usajobs_parses_results(mocker):
    mocker.patch("app.discovery.usajobs.requests.get", return_value=_response(200, {
        "SearchResult": {"SearchResultItems": [{
            "MatchedObjectId": "abc",
            "MatchedObjectDescriptor": {
                "PositionTitle": "Data Scientist", "OrganizationName": "Dept of Example",
                "PositionLocationDisplay": "Washington, DC", "PositionURI": "https://usajobs.gov/jobs/abc",
                "PositionRemuneration": [{"MinimumRange": "90000", "MaximumRange": "120000"}],
                "PositionSchedule": [{"Name": "Full-time"}],
                "PublicationStartDate": "2026-08-01",
                "UserArea": {"Details": {"JobSummary": "Analyze federal data."}},
            },
        }]},
    }))

    results = search_usajobs(DiscoveryQuery(keywords=["Data Scientist"], limit_per_source=10), api_key="key", user_agent_email="me@example.com")
    assert len(results) == 1
    job = results[0]
    assert job.external_job_id == "abc"
    assert job.salary_min == 90000
    assert job.salary_max == 120000
    assert job.employment_type == JobEmploymentType.FULL_TIME


# --- Remotive ------------------------------------------------------------


def test_remotive_parses_results_and_passes_first_keyword_as_search(mocker):
    get = mocker.patch("app.discovery.remotive.requests.get", return_value=_response(200, {
        "jobs": [{
            "id": 555, "title": "Machine Learning Engineer", "company_name": "RemoteCo",
            "url": "https://remotive.com/remote-jobs/555", "job_type": "full_time",
            "candidate_required_location": "Worldwide",
            "description": "<p>" + "Great ML role. " * 20 + "</p>",
            "publication_date": "2026-08-10T00:00:00",
        }],
    }))

    results = search_remotive(DiscoveryQuery(keywords=["Machine Learning", "AI Engineer"], limit_per_source=10))
    assert len(results) == 1
    job = results[0]
    assert job.external_job_id == "555"
    assert job.employment_type == JobEmploymentType.FULL_TIME
    assert job.workplace_type == WorkplaceType.REMOTE
    assert job.posted_date == "2026-08-10"
    assert get.call_args.kwargs["params"]["search"] == "Machine Learning"


# --- Arbeitnow -------------------------------------------------------------


def test_arbeitnow_filters_by_keyword_and_unescapes_description(mocker):
    mocker.patch("app.discovery.arbeitnow.requests.get", return_value=_response(200, {
        "data": [
            {
                "slug": "ml-engineer-acme", "title": "Machine Learning Engineer", "company_name": "Acme",
                "url": "https://www.arbeitnow.com/jobs/companies/acme/ml-engineer-acme",
                "tags": ["Machine Learning"], "remote": True, "location": "Worldwide",
                "description": "&lt;p&gt;" + "Build ML systems. " * 20 + "&lt;/p&gt;",
                "created_at": 1723276800,
            },
            {
                "slug": "sales-rep-other", "title": "Sales Rep", "company_name": "OtherCo",
                "url": "https://www.arbeitnow.com/jobs/companies/otherco/sales-rep-other",
                "tags": [], "remote": False, "location": "NYC", "description": "", "created_at": 1723276800,
            },
        ],
    }))

    results = search_arbeitnow(DiscoveryQuery(keywords=["Machine Learning"], limit_per_source=10))
    assert len(results) == 1
    job = results[0]
    assert job.external_job_id == "ml-engineer-acme"
    assert job.workplace_type == WorkplaceType.REMOTE
    assert job.posted_date == "2024-08-10"
    assert "<p>" not in job.description and "&lt;" not in job.description
    assert "Build ML systems." in job.description


# --- Himalayas ---------------------------------------------------------


def test_himalayas_parses_results(mocker):
    get = mocker.patch("app.discovery.himalayas.requests.get", return_value=_response(200, {
        "jobs": [{
            "title": "Machine Learning Engineer", "companyName": "RemoteCo",
            "guid": "https://himalayas.app/companies/remoteco/jobs/ml-engineer",
            "applicationLink": "https://himalayas.app/companies/remoteco/jobs/ml-engineer",
            "employmentType": "Full Time", "locationRestrictions": ["United States", "Canada"],
            "minSalary": 100000, "maxSalary": 140000, "currency": "USD",
            "description": "<p>" + "Great ML role. " * 20 + "</p>",
            "pubDate": 1723276800,
        }],
    }))

    results = search_himalayas(DiscoveryQuery(keywords=["Machine Learning"], locations=["United States"], limit_per_source=10))
    assert len(results) == 1
    job = results[0]
    assert job.external_job_id == "https://himalayas.app/companies/remoteco/jobs/ml-engineer"
    assert job.location == "United States, Canada"
    assert job.employment_type == JobEmploymentType.FULL_TIME
    assert job.workplace_type == WorkplaceType.REMOTE
    assert job.salary_min == 100000
    assert job.posted_date == "2024-08-10"
    assert get.call_args.kwargs["params"]["q"] == "Machine Learning"
    assert get.call_args.kwargs["params"]["country"] == "United States"


# --- ingest_discovered_job (dedup) ----------------------------------------


def _sample_discovered(**overrides) -> DiscoveredJob:
    defaults = dict(
        source="greenhouse", external_job_id="ext-1", title="ML Engineer", company="Acme",
        url="https://acme.com/jobs/1", description="A" * 250,
    )
    defaults.update(overrides)
    return DiscoveredJob(**defaults)


def test_ingest_discovered_job_creates_new_job(db_session):
    result = ingest_discovered_job(db_session, _sample_discovered())
    assert result.created is True
    assert result.job.title == "ML Engineer"
    assert result.job.company == "Acme"
    assert result.job.source == "greenhouse"
    assert result.job.external_job_id == "ext-1"
    assert result.job.status.value == "discovered"


def test_ingest_discovered_job_dedups_by_external_id(db_session):
    first = ingest_discovered_job(db_session, _sample_discovered())
    second = ingest_discovered_job(db_session, _sample_discovered(title="Different title now"))
    assert second.created is False
    assert second.job.id == first.job.id


def test_ingest_discovered_job_dedups_by_canonical_url_across_sources(db_session):
    first = ingest_discovered_job(db_session, _sample_discovered())
    second = ingest_discovered_job(db_session, _sample_discovered(source="lever", external_job_id="different-id"))
    assert second.created is False
    assert second.job.id == first.job.id


# --- discovery_service orchestration ---------------------------------------


def test_build_query_prefers_goal_over_profile(client, db_session, profile):
    client.put("/profile", json={"target_roles": ["Profile Role"], "preferred_locations": ["Profile City"]})
    client.put("/intelligence/goals", json={"target_roles": ["Goal Role"], "target_companies": ["Acme"]})

    query = build_query(db_session)
    assert query.keywords == ["Goal Role"]
    assert query.companies == ["Acme"]


def test_build_query_falls_back_to_profile(client, db_session, profile):
    client.put("/profile", json={"target_roles": ["Profile Role"], "preferred_locations": ["Profile City"]})

    query = build_query(db_session)
    assert query.keywords == ["Profile Role"]
    assert query.locations == ["Profile City"]
    assert query.companies == []


def test_run_discovery_isolates_per_source_errors_and_records_results(db_session, mocker):
    mocker.patch(
        "app.services.discovery_service.search_remoteok",
        return_value=[_sample_discovered(source="remoteok", external_job_id="ok-1")],
    )
    mocker.patch("app.services.discovery_service.search_adzuna", side_effect=DiscoverySourceError("Adzuna is not configured"))

    run = run_discovery(db_session, trigger=DiscoveryTrigger.MANUAL, sources=["remoteok", "adzuna"], query=DiscoveryQuery())

    assert run.jobs_found == 1
    assert run.jobs_created == 1
    assert run.results["remoteok"]["created"] == 1
    assert run.results["adzuna"]["error"] == "Adzuna is not configured"
    assert run.trigger == DiscoveryTrigger.MANUAL


def test_run_discovery_reports_missing_companies_without_error(db_session):
    run = run_discovery(db_session, trigger=DiscoveryTrigger.MANUAL, sources=["greenhouse"], query=DiscoveryQuery(companies=[]))
    assert run.results["greenhouse"]["error"] is None
    assert run.results["greenhouse"]["found"] == 0
    assert "target companies" in run.results["greenhouse"]["note"].lower()


def test_run_discovery_rejects_unknown_source(db_session):
    with pytest.raises(DiscoveryInputError):
        run_discovery(db_session, trigger=DiscoveryTrigger.MANUAL, sources=["not_a_real_source"])


def test_run_discovery_dedups_across_the_same_run(db_session, mocker):
    same_job = _sample_discovered(source="remoteok", external_job_id="dupe-1")
    mocker.patch("app.services.discovery_service.search_remoteok", return_value=[same_job])
    mocker.patch("app.services.discovery_service.search_weworkremotely", return_value=[same_job])

    run = run_discovery(db_session, trigger=DiscoveryTrigger.MANUAL, sources=["remoteok", "weworkremotely"], query=DiscoveryQuery())
    assert run.jobs_created == 1
    assert run.jobs_found == 2


# --- API endpoints -----------------------------------------------------


def test_discovery_sources_endpoint(client):
    # Deliberately overrides whatever real keys .env may have (a
    # developer's own local Adzuna/USAJobs credentials, say) so this test
    # exercises the "not configured" branch regardless of the environment
    # it happens to run in -- mirrors conftest.py's allow_real_submit
    # pattern of mutating the cached Settings singleton for one test.
    from app.config import get_settings

    settings = get_settings()
    original = (settings.adzuna_app_id, settings.adzuna_app_key, settings.usajobs_api_key, settings.usajobs_user_agent_email)
    settings.adzuna_app_id = settings.adzuna_app_key = settings.usajobs_api_key = settings.usajobs_user_agent_email = ""
    try:
        resp = client.get("/discovery/sources")
    finally:
        settings.adzuna_app_id, settings.adzuna_app_key, settings.usajobs_api_key, settings.usajobs_user_agent_email = original

    assert resp.status_code == 200
    sources = {s["source"]: s for s in resp.json()}
    assert set(sources) == {
        "greenhouse", "lever", "remoteok", "weworkremotely", "adzuna", "usajobs",
        "remotive", "arbeitnow", "himalayas",
    }
    assert sources["greenhouse"]["configured"] is True
    assert sources["adzuna"]["configured"] is False


def test_run_discovery_endpoint_and_list_runs(client, mocker):
    mocker.patch(
        "app.services.discovery_service.search_remoteok",
        return_value=[_sample_discovered(source="remoteok", external_job_id="api-1")],
    )

    resp = client.post("/discovery/run", json={"sources": ["remoteok"], "keywords": ["ML"]})
    assert resp.status_code == 201
    body = resp.json()
    assert body["jobs_created"] == 1
    assert body["trigger"] == "manual"
    run_id = body["id"]

    list_resp = client.get("/discovery/runs")
    assert list_resp.status_code == 200
    assert list_resp.json()["total"] == 1

    get_resp = client.get(f"/discovery/runs/{run_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == run_id


def test_get_discovery_run_404(client):
    resp = client.get("/discovery/runs/999999")
    assert resp.status_code == 404


def test_run_discovery_endpoint_rejects_unknown_source(client):
    resp = client.post("/discovery/run", json={"sources": ["not_real"]})
    assert resp.status_code == 422
