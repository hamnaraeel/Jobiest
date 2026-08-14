# Career Agent

An AI-powered job application agent, built step by step.

- **Step 1 — Career Profile & Knowledge Base**: a structured, verified
  store of your career facts (education, experience, projects, skills,
  research, certifications, achievements) with an evidence system that
  prevents any future AI layer from inventing experience you don't have.
  See [`docs/career-profile-schema.md`](docs/career-profile-schema.md).
- **Step 2 — Job Ingestion, Analysis & Matching**: paste a job URL or
  description in, get a deterministic, explainable fit score out. See
  [`docs/job-matching-schema.md`](docs/job-matching-schema.md).

Neither step includes CV/cover-letter generation, browser automation,
application submission, or autonomous agents — those come later.

## 1. Installation

Requires Python 3.11+ and PostgreSQL 14+ with the [pgvector](https://github.com/pgvector/pgvector)
extension available.

```bash
cd career-agent/backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 2. PostgreSQL setup

Create a database and enable pgvector:

```bash
createdb career_agent
psql -d career_agent -c "CREATE EXTENSION IF NOT EXISTS vector;"
```

(The first Alembic migration also runs `CREATE EXTENSION IF NOT EXISTS
vector` itself, so this manual step is a convenience, not a hard
requirement — either way works.)

If you don't have a local Postgres server, Docker is the fastest path:

```bash
docker run -d --name career-agent-postgres \
  -e POSTGRES_USER=postgres -e POSTGRES_PASSWORD=postgres \
  -e POSTGRES_DB=career_agent -p 5432:5432 \
  pgvector/pgvector:pg16
```

## 3. Environment variables

```bash
cp .env.example .env
```

```
DATABASE_URL=postgresql+psycopg2://postgres:postgres@localhost:5432/career_agent
OPENAI_API_KEY=
```

`OPENAI_API_KEY` powers job analysis (`POST /jobs/{id}/analyze`) and the
optional match-explanation call. Everything else -- profile management,
job ingestion/cleaning/storage, deduplication, the dashboard, and the
deterministic match score itself -- works with no key set. Calling an
AI-dependent endpoint without a key returns a clear `503` explaining
what's missing, never a crash or a silent fallback pretending to be real
analysis. An optional `OPENAI_MODEL` (default `gpt-4o-mini`) selects the
model used for both AI calls.

## 4. Database migration

```bash
alembic upgrade head
```

## 5. Running FastAPI

```bash
uvicorn app.main:app --reload
```

The API is now at `http://localhost:8000`, interactive docs at
`http://localhost:8000/docs`.

## 6. Load your data

`data/career_profile.json` contains placeholder data only (`YOUR_NAME`,
`YOUR_COMPANY`, etc — see `data/README.md`). Replace the placeholders with
your real, verifiable information, then import it:

```bash
curl -X POST http://localhost:8000/profile/import \
  -H "Content-Type: application/json" \
  --data @data/career_profile.json
```

## 7. API examples

Create a profile directly instead of importing:

```bash
curl -X POST http://localhost:8000/profile \
  -H "Content-Type: application/json" \
  -d '{
    "full_name": "Jane Doe",
    "professional_title": "Machine Learning Engineer",
    "email": "jane@example.com",
    "target_roles": ["Machine Learning Engineer", "AI Engineer"],
    "years_of_experience": 2
  }'
```

Add a verified skill:

```bash
curl -X POST http://localhost:8000/skills \
  -H "Content-Type: application/json" \
  -d '{
    "profile_id": 1, "name": "PyTorch", "category": "ML/DL",
    "proficiency": "advanced", "years_used": 2, "verified": true
  }'
```

Add experience with individually-stored bullets:

```bash
curl -X POST http://localhost:8000/experience \
  -H "Content-Type: application/json" \
  -d '{
    "profile_id": 1, "company": "Acme AI", "role": "ML Engineer",
    "employment_type": "full_time", "start_date": "2023-01-01",
    "currently_working": true,
    "bullets": [
      {"bullet": "Developed deep learning models for medical image segmentation using PyTorch.",
       "skills": ["PyTorch", "Deep Learning", "Medical Imaging"]}
    ]
  }'
```

Attach evidence to a fact (making it possible to responsibly mark it
`verified`):

```bash
curl -X POST http://localhost:8000/evidence \
  -H "Content-Type: application/json" \
  -d '{
    "profile_id": 1, "source_type": "GitHub", "source_name": "github.com/jane/segmentation-project",
    "links": [{"entity_type": "skill", "entity_id": 1}]
  }'
```

Export the full profile:

```bash
curl http://localhost:8000/profile/export | python3 -m json.tool
```

Full Step 1 endpoint list: `GET/POST/PUT /profile`, `GET /profile/export`,
`POST /profile/import`, and `GET/POST` for `/skills`, `/education`,
`/experience`, `/projects`, `/certifications`, `/achievements`,
`/research`, `/evidence`.

## 7b. Step 2: jobs, analysis, matching

Ingest a job from a pasted description (works with no API key):

```bash
curl -X POST http://localhost:8000/jobs \
  -H "Content-Type: application/json" \
  -d '{"description": "Machine Learning Engineer at Example Company. Requirements: 2+ years Python, PyTorch, Computer Vision. Preferred: AWS, Docker."}'
```

...or from a URL (fetched, cleaned, and stored; returns
`fetch_notice: {"status": "manual_input_required", ...}` instead of
failing if the page can't be retrieved or looks JavaScript-only):

```bash
curl -X POST http://localhost:8000/jobs \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com/careers/ml-engineer"}'
```

Run AI analysis (requires `OPENAI_API_KEY`; extracts requirements, one
LLM call):

```bash
curl -X POST http://localhost:8000/jobs/1/analyze
```

Run the deterministic match against your career profile (auto-runs
analysis first if it hasn't happened yet; works with no API key once a
job is already analyzed -- the explanation prose just falls back to a
template):

```bash
curl -X POST http://localhost:8000/jobs/1/match | python3 -m json.tool
```

```json
{
  "job": {"title": "Machine Learning Engineer", "company": "Example Company", "location": null},
  "score": 88,
  "recommendation": "apply",
  "strengths": ["Python", "PyTorch", "Computer Vision"],
  "weaknesses": ["AWS"],
  "matched_requirements": [
    {"requirement": "Python", "category": "technical_skill", "importance": "high",
     "required": true, "status": "matched", "evidence": ["Skill: Python"], "reason": null}
  ],
  "partial_requirements": [],
  "missing_requirements": [
    {"requirement": "AWS", "category": "technical_skill", "importance": "medium",
     "required": false, "status": "missing", "evidence": [], "reason": "Not found in career profile."}
  ],
  "unknown_requirements": [],
  "critical_gaps": [],
  "summary": "Overall alignment score: 88/100 (apply). Strong matches: Python, PyTorch, Computer Vision.",
  "created_at": "2026-01-01T12:00:00Z",
  "updated_at": "2026-01-01T12:00:00Z"
}
```

Retrieve the stored result later without recomputing:

```bash
curl http://localhost:8000/jobs/1/match
```

Browse the dashboard:

```bash
curl "http://localhost:8000/jobs?min_score=80&recommendation=apply"
curl "http://localhost:8000/jobs?company=Example&search=PyTorch"
```

Full Step 2 endpoint list: `POST/GET /jobs`, `GET /jobs/{id}`,
`GET /jobs/{id}/requirements`, `POST /jobs/{id}/analyze`,
`POST/GET /jobs/{id}/match`.

### Manual end-to-end demo

```bash
python -m app.scripts.analyze_job ../data/test_job_description.txt
```

Requires `OPENAI_API_KEY` set and a career profile already created.
Prints the extracted requirements and the match result in plain text.

## 8. Testing

Tests run against a real PostgreSQL database (with pgvector) — point
`DATABASE_URL` at a disposable database before running them; the suite
drops and recreates the schema itself:

```bash
export DATABASE_URL=postgresql+psycopg2://postgres:postgres@localhost:5432/career_agent_test
pytest -v
```

No `OPENAI_API_KEY` is needed to run the suite -- every test that would
otherwise call OpenAI mocks the client (`pytest-mock`'s `mocker` fixture)
and every test that would otherwise hit a real URL mocks `requests.get`.
Tests never depend on real network or API calls.

## Project structure

```
career-agent/
├── backend/
│   ├── app/
│   │   ├── main.py               FastAPI app, router registration, logging config
│   │   ├── config.py              Settings (DATABASE_URL, OPENAI_API_KEY, OPENAI_MODEL)
│   │   ├── api/                   One router per resource (incl. jobs.py)
│   │   ├── models/                SQLAlchemy models + shared enums
│   │   ├── schemas/                Pydantic Create/Update/Read schemas
│   │   ├── services/
│   │   │   ├── profile_service.py       Step 1: CRUD, export/import
│   │   │   ├── validation_service.py    Step 1: evidence lookups, truth rules
│   │   │   ├── job_ingestion_service.py Step 2: fetch/clean/store/dedup
│   │   │   ├── job_parser.py            Step 2: URL fetch + HTML cleaning
│   │   │   ├── job_analysis_service.py  Step 2: AI extraction -> requirements
│   │   │   └── job_matching_service.py  Step 2: deterministic scoring engine
│   │   ├── ai/
│   │   │   ├── client.py          OpenAI client + config-error handling
│   │   │   ├── prompts.py         Versioned prompts (JOB_ANALYSIS_PROMPT_V1, ...)
│   │   │   └── structured_outputs.py  Pydantic schemas the LLM output must match
│   │   ├── scripts/
│   │   │   └── analyze_job.py     Manual end-to-end demo script
│   │   └── db/                    Engine/session, declarative Base
│   ├── alembic/                   Migrations (Step 1 schema, then Step 2 schema)
│   ├── tests/                     pytest suite
│   ├── requirements.txt
│   └── .env.example
├── data/
│   ├── career_profile.json        Placeholder seed data
│   ├── test_job_description.txt   Sample job posting for the demo script
│   └── README.md                  How to fill in career_profile.json
├── docs/
│   ├── career-profile-schema.md   Step 1: full schema + verification rules
│   └── job-matching-schema.md     Step 2: dedup, scoring, match statuses
└── README.md
```

## What's next (not built yet)

CV tailoring, cover letter generation, a user-approval workflow, browser
automation for application submission, and application/outcome tracking.
The schema is deliberately structured (foreign keys, evidence links,
reserved embedding columns, `get_relevant_career_data()` isolated behind
one function) so those steps can be added without reshaping what already
exists.
