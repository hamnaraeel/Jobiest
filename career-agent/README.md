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
- **Step 3 — CV Customization, Versioning & PDF Generation**: generate a
  job-tailored CV where every bullet traces back to a real, verified
  profile row, validated deterministically before it's ever rendered to
  LaTeX and compiled to PDF. See [`docs/cv-generation.md`](docs/cv-generation.md).

None of these steps include cover-letter generation, browser automation,
application submission, or autonomous agents — those come later.

## 1. Installation

Requires Python 3.11+, PostgreSQL 14+ with the [pgvector](https://github.com/pgvector/pgvector)
extension available, and a LaTeX distribution providing `pdflatex` (only
needed for actual PDF compilation in Step 3 -- everything else works
without it).

```bash
cd career-agent/backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

On macOS, [BasicTeX](https://tug.org/mactex/morepackages.html) is a much
smaller install than full MacTeX and is enough for the default template:

```bash
brew install --cask basictex
# open a new terminal afterward so PATH picks up pdflatex
```

If `pdflatex` isn't installed or isn't on `PATH`, `POST /jobs/{id}/cv/generate`
still runs the full plan/content/validation pipeline and stores the CV
row -- it just returns a clear PDF-compilation error inside `warnings`
instead of a `pdf_path`, rather than failing the whole request. Use
`POST /jobs/{id}/cv/preview` (which never attempts PDF compilation) to
review generated content without needing `pdflatex` at all.

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
OPENAI_MODEL=gpt-4o-mini
CV_MAX_PAGES=1
CV_STORAGE_DIR=../data/cvs
PDFLATEX_PATH=pdflatex
```

`OPENAI_API_KEY` powers job analysis, CV planning/content generation, and
the optional match-explanation call. Everything else -- profile
management, job ingestion/cleaning/storage, deduplication, the dashboard,
and the deterministic match/CV-validation logic itself -- works with no
key set. Calling an AI-dependent endpoint without a key returns a clear
`503` explaining what's missing, never a crash or a silent fallback
pretending to be real analysis. `CV_MAX_PAGES` is read by the CV
generation service as the target page budget; `CV_STORAGE_DIR` is where
`.tex`/`.pdf` files land (see `data/cvs/`); `PDFLATEX_PATH` lets you point
at a non-standard `pdflatex` binary if it's not on `PATH`.

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

## 7c. Step 3: CV generation, versioning, comparison

Generate a tailored CV for an already-analyzed job (requires
`OPENAI_API_KEY`; runs plan + content generation + validation + LaTeX +
PDF compilation, and stores a new version):

```bash
curl -X POST http://localhost:8000/jobs/1/cv/generate | python3 -m json.tool
```

Preview the generated content without compiling a PDF (useful without
`pdflatex` installed, or to review before spending a compile on it):

```bash
curl -X POST http://localhost:8000/jobs/1/cv/preview | python3 -m json.tool
```

```json
{
  "version_id": 1,
  "summary": "Machine Learning Engineer with hands-on experience developing deep learning models for medical image segmentation using PyTorch.",
  "skills": [{"category": "ML/DL", "skills": ["PyTorch"]}],
  "experience": [{"experience_id": 1, "company": "Acme AI", "role": "Machine Learning Engineer",
    "bullets": [{"text": "Developed deep learning models for medical image segmentation using PyTorch.",
                 "source_type": "experience_bullet", "source_id": 1, "verified": true}]}],
  "projects": [{"project_id": 1, "name": "Hirschsprung Disease Segmentation",
    "bullets": [{"text": "Improved segmentation accuracy (+6.2% Dice score)",
                 "source_type": "project_result", "source_id": 1, "verified": true}]}],
  "education": [],
  "warnings": []
}
```

Every bullet carries `source_type`/`source_id`/`verified` -- see
`docs/examples/cv_example.json` for a complete real example.

List, fetch, download, and review versions:

```bash
curl "http://localhost:8000/cvs?job_id=1"
curl http://localhost:8000/cvs/1
curl http://localhost:8000/cvs/1/download -o cv.pdf
curl http://localhost:8000/cvs/1/comparison | python3 -m json.tool
```

Human approval workflow -- nothing is ever auto-approved:

```bash
curl -X PATCH http://localhost:8000/cvs/1/status -H "Content-Type: application/json" -d '{"status": "approved"}'
```

`DELETE /cvs/{id}` archives a version (`status: archived`) rather than
deleting the row or the PDF -- old versions are never destroyed
automatically.

Full Step 3 endpoint list: `POST /jobs/{id}/cv/generate`,
`POST /jobs/{id}/cv/preview`, `GET /cvs`, `GET /cvs/{id}`,
`GET /cvs/{id}/download`, `GET /cvs/{id}/comparison`,
`PATCH /cvs/{id}/status`, `DELETE /cvs/{id}`.

## 8. Testing

Tests run against a real PostgreSQL database (with pgvector) — point
`DATABASE_URL` at a disposable database before running them; the suite
drops and recreates the schema itself:

```bash
export DATABASE_URL=postgresql+psycopg2://postgres:postgres@localhost:5432/career_agent_test
pytest -v
```

No `OPENAI_API_KEY` is needed to run the suite -- every test that would
otherwise call OpenAI mocks the client (`pytest-mock`'s `mocker` fixture,
or a hand-built fake client for the CV generation tests) and every test
that would otherwise hit a real URL mocks `requests.get`. Tests never
depend on real network or API calls. PDF-compilation tests are skipped
automatically (`pytest.mark.skipif`) when `pdflatex` isn't on `PATH` --
everything else in the CV pipeline (planning, content generation,
validation, LaTeX rendering/escaping) is still fully tested either way.

## Project structure

```
career-agent/
├── backend/
│   ├── app/
│   │   ├── main.py               FastAPI app, router registration, logging config
│   │   ├── config.py              Settings (incl. CV_MAX_PAGES, CV_STORAGE_DIR, PDFLATEX_PATH)
│   │   ├── api/                   One router per resource (incl. jobs.py, cvs.py)
│   │   ├── models/                SQLAlchemy models + shared enums
│   │   ├── schemas/                Pydantic Create/Update/Read schemas
│   │   ├── services/
│   │   │   ├── profile_service.py         Step 1: CRUD, export/import
│   │   │   ├── validation_service.py      Step 1: evidence lookups, truth rules
│   │   │   ├── job_ingestion_service.py   Step 2: fetch/clean/store/dedup
│   │   │   ├── job_parser.py              Step 2: URL fetch + HTML cleaning
│   │   │   ├── job_analysis_service.py    Step 2: AI extraction -> requirements
│   │   │   ├── job_matching_service.py    Step 2: deterministic scoring engine
│   │   │   ├── cv_customization_service.py Step 3: plan -> content -> assemble orchestration
│   │   │   ├── cv_validation_service.py    Step 3: deterministic hallucination detection
│   │   │   ├── cv_render_service.py        Step 3: LaTeX escaping/rendering + pdflatex
│   │   │   └── cv_comparison_service.py    Step 3: change tracking + comparison
│   │   ├── ai/
│   │   │   ├── client.py          OpenAI client + config-error handling
│   │   │   ├── prompts.py         Step 2 prompts (JOB_ANALYSIS_PROMPT_V1, ...)
│   │   │   ├── structured_outputs.py  Step 2 LLM output schemas
│   │   │   ├── cv_prompts.py       Step 3 prompts (CV_PLAN_PROMPT_V1, ...)
│   │   │   └── cv_structured_outputs.py  Step 3 LLM output schemas
│   │   ├── scripts/
│   │   │   └── analyze_job.py     Manual end-to-end demo script (Step 2)
│   │   └── db/                    Engine/session, declarative Base
│   ├── alembic/                   Migrations (Step 1, then Step 2, then Step 3 schema)
│   ├── tests/                     pytest suite
│   ├── requirements.txt
│   └── .env.example
├── cv_templates/
│   ├── ats/ml_engineer.tex        Default ATS-friendly LaTeX template
│   └── README.md                  How the template placeholder system works
├── data/
│   ├── career_profile.json        Placeholder seed data
│   ├── test_job_description.txt   Sample job posting for the demo script
│   ├── cvs/                       Generated .tex/.pdf output (job_{id}/cv_v{n}.*)
│   └── README.md                  How to fill in career_profile.json
├── docs/
│   ├── career-profile-schema.md   Step 1: full schema + verification rules
│   ├── job-matching-schema.md     Step 2: dedup, scoring, match statuses
│   ├── cv-generation.md           Step 3: pipeline, validation, versioning, approval
│   └── examples/                  Real generated cv_example.json / cv_example.tex
└── README.md
```

## What's next (not built yet)

Cover letter generation, company-specific motivation/application-answer
generation, browser automation for application submission, and
application/outcome tracking. `CVVersion` (id, status, PDF path, JSON
content, match scores, job id) is the exact handoff surface a future step
would consume -- nothing about it needs to change shape to support that.
