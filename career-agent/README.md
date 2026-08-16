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
- **Step 4 — Cover Letters & Application Answers**: generate a tailored
  cover letter and answer common (or your own) application questions,
  running entirely on a local [Ollama](https://ollama.com) model -- no
  paid API. See [`docs/cover-letters-and-applications.md`](docs/cover-letters-and-applications.md).
- **Step 5 — Browser-Based Application Assistant**: a real Playwright
  browser detects form fields, auto-fills only high-confidence matches to
  your verified profile/approved Step 4 answers, uploads only *approved*
  CV/cover-letter PDFs, and stops for you at logins/CAPTCHAs and before
  any real submit click -- `DRY_RUN=true` by default, and a real click
  additionally requires your explicit `POST
  /applications/{id}/approve-submission`. See
  [`docs/browser-application-assistant.md`](docs/browser-application-assistant.md).

This is an assisted workflow, not an autonomous agent -- nothing is ever
submitted without a human reviewing it first.

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

Step 4 (cover letters, application answers) additionally needs
[Ollama](https://ollama.com) with a model pulled locally -- no OpenAI key,
no paid API of any kind:

```bash
brew install ollama
brew services start ollama          # or: ollama serve
ollama pull llama3.1                # or any model you prefer
```

Step 5 (browser-based application assistant) additionally needs a
Playwright browser binary:

```bash
python3 -m playwright install chromium
```

> **macOS 12 (Monterey) note:** recent Playwright releases have dropped
> Chromium binary support for macOS 12. `requirements.txt` pins
> `playwright==1.48.0`, the newest version confirmed to still ship a
> mac12-compatible Chromium build (verified with a real
> `sync_playwright` smoke test). If you're on macOS 13+ you can use a
> newer Playwright version freely; on macOS 12, don't bump past 1.48.x
> without re-verifying `playwright install chromium` still succeeds.

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
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3.1
COVER_LETTER_MIN_WORDS=250
COVER_LETTER_MAX_WORDS=400
APPLICATION_MATERIALS_DIR=../data/application_materials
DRY_RUN=true
BROWSER_HEADLESS=false
BROWSER_TYPE=chromium
BROWSER_PROFILE_DIR=../data/browser_profile
BROWSER_SCREENSHOTS=false
APPLICATION_SESSIONS_DIR=../data/application_sessions
FIELD_CONFIDENCE_HIGH=0.90
FIELD_CONFIDENCE_MEDIUM=0.70
```

`OPENAI_API_KEY` powers job analysis and CV planning/content generation
(Steps 2-3 only). `OLLAMA_MODEL` powers cover letters and application
answers (Step 4) -- entirely separate from OpenAI, no paid API, no key.
Everything else -- profile management, job ingestion/cleaning/storage,
deduplication, the dashboard, and every deterministic validation/matching
step -- works with neither configured. Calling an AI-dependent endpoint
without its provider configured returns a clear `503` explaining what's
missing, never a crash or a silent fallback pretending to be real output.
`DRY_RUN` (Step 5) gates whether the browser assistant is ever allowed to
click a real submit button -- leave it `true` until you've reviewed the
workflow yourself; `BROWSER_HEADLESS=false` shows the browser window so
you can watch/log in/solve a CAPTCHA manually.
`CV_MAX_PAGES` is the CV generator's target page budget; `CV_STORAGE_DIR`/
`APPLICATION_MATERIALS_DIR` are where generated `.tex`/`.pdf` files land
(see `data/cvs/README.md`, `data/application_materials/README.md`);
`PDFLATEX_PATH` lets you point at a non-standard `pdflatex` binary if it's
not on `PATH`; `COVER_LETTER_MIN_WORDS`/`MAX_WORDS` set the target length
range (`length: "short"|"medium"|"long"` in the generate request nudges
within/around that range).

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

## 7d. Step 4: cover letters & application answers (local Ollama)

A cover letter needs an **approved** CV first:

```bash
curl -X PATCH http://localhost:8000/cvs/1/status -H "Content-Type: application/json" -d '{"status": "approved"}'
curl -X POST http://localhost:8000/jobs/1/cover-letter/generate | python3 -m json.tool
```

Optional style/length/focus/instructions (validated -- invalid values are
rejected, and instructions can never override truthfulness: "add AWS" is
rejected outright if AWS isn't verified):

```bash
curl -X POST http://localhost:8000/jobs/1/cover-letter/generate \
  -H "Content-Type: application/json" \
  -d '{"style": "concise", "length": "short", "focus": ["computer vision"], "instructions": "Emphasize my research experience."}'
```

Download as text (default) or PDF (compiled lazily on first request):

```bash
curl http://localhost:8000/cover-letters/1/download -o letter.txt
curl "http://localhost:8000/cover-letters/1/download?format=pdf" -o letter.pdf
```

Approve, regenerate a new version, or see version history:

```bash
curl -X PATCH http://localhost:8000/cover-letters/1/status -H "Content-Type: application/json" -d '{"status": "approved"}'
curl -X POST http://localhost:8000/cover-letters/1/regenerate -H "Content-Type: application/json" -d '{"length": "long"}'
curl http://localhost:8000/cover-letters/1/versions
```

Application questions -- create, then generate an answer (character/word
limits are enforced in Python, with automatic LLM-assisted shortening if
the first draft is too long):

```bash
curl -X POST http://localhost:8000/jobs/1/application-questions \
  -H "Content-Type: application/json" \
  -d '{"question": "Describe your experience with PyTorch.", "character_limit": 500}'

curl -X POST http://localhost:8000/jobs/1/application-questions/1/answer | python3 -m json.tool
```

Salary/authorization/relocation/availability questions never guess --
they return `manual_input_required` until you explicitly set the
corresponding profile field:

```bash
curl -X POST http://localhost:8000/jobs/1/application-questions \
  -H "Content-Type: application/json" -d '{"question": "What is your salary expectation?"}'
curl -X POST http://localhost:8000/jobs/1/application-questions/2/answer
# {"status": "manual_input_required", "question_type": "salary", "reason": "No salary expectation is configured on the career profile."}

curl -X PUT http://localhost:8000/profile -H "Content-Type: application/json" -d '{"salary_expectation": "$120,000 - $140,000 USD"}'
# now the same question can generate a real answer
```

The full picture for a job -- job, match, CV, cover letter, every
question's answer, and whether it's all actually approved:

```bash
curl http://localhost:8000/jobs/1/application-materials | python3 -m json.tool
```

Full Step 4 endpoint list: `POST /jobs/{id}/cover-letter/generate`,
`GET /cover-letters/{id}`, `GET /cover-letters/{id}/versions`,
`GET /cover-letters/{id}/download`, `POST /cover-letters/{id}/regenerate`,
`PATCH /cover-letters/{id}/status`, `POST/GET /jobs/{id}/application-questions`,
`POST /jobs/{id}/application-questions/{id}/answer`,
`GET /application-answers/{id}`, `PATCH /application-answers/{id}/status`,
`GET /jobs/{id}/application-materials`.

See `docs/examples/cover_letter_example.txt` and
`docs/examples/application_answers_example.json` for real generated
output.

## 7e. Step 5: browser-based application assistant

Create an application attempt for an already-analyzed job (defaults to
the job's own URL and the latest approved CV/cover letter):

```bash
curl -X POST http://localhost:8000/jobs/1/apply | python3 -m json.tool
```

Open a real browser and start the workflow:

```bash
curl -X POST http://localhost:8000/applications/1/start-browser
curl -X POST http://localhost:8000/applications/1/analyze-page | python3 -m json.tool
```

If `captcha_detected` or `login_required` comes back `true`, the
application's status becomes `blocked`/`needs_user_input` and nothing
further happens automatically -- complete that step by hand in the
browser window, then call `analyze-page` again.

Auto-fill the high-confidence fields and upload approved materials, then
review what still needs you:

```bash
curl -X POST http://localhost:8000/applications/1/fill | python3 -m json.tool
curl http://localhost:8000/applications/1/review | python3 -m json.tool
```

Provide a value for anything flagged `user_review_required` (salary,
authorization, relocation, and similar sensitive questions are *never*
auto-filled, by design):

```bash
curl -X POST http://localhost:8000/applications/1/fields/3/input \
  -H "Content-Type: application/json" -d '{"value": "$120,000 - $140,000 USD"}'
```

Submitting is always simulated while `DRY_RUN=true` (the default), no
matter what else is true:

```bash
curl -X POST http://localhost:8000/applications/1/approve-submission
curl -X POST http://localhost:8000/applications/1/submit
# {"submitted": false, "dry_run": true, "reason": "DRY_RUN is enabled -- submission is simulated, ..."}
```

To actually submit, set `DRY_RUN=false` in `.env`, restart the app, and
call approve-submission again (it's per-application and isn't implied by
anything else):

```bash
curl -X POST http://localhost:8000/applications/1/approve-submission
curl -X POST http://localhost:8000/applications/1/submit | python3 -m json.tool
# {"submitted": true, "confirmation_reference": "..."}
```

`GET /applications/1/events` returns the full append-only audit log of
everything the agent did, in order.

Full Step 5 endpoint list: `POST /jobs/{id}/apply`, `GET /applications`,
`GET /applications/{id}`, `GET /applications/{id}/events`,
`POST /applications/{id}/start-browser`,
`POST /applications/{id}/analyze-page`, `POST /applications/{id}/fill`,
`GET /applications/{id}/review`,
`POST /applications/{id}/fields/{field_id}/input`,
`POST /applications/{id}/approve-submission`,
`POST /applications/{id}/submit`, `POST /applications/{id}/pause`,
`POST /applications/{id}/resume`, `POST /applications/{id}/cancel`.

See `docs/browser-application-assistant.md` for the full safety model and
architecture.

## 8. Testing

Tests run against a real PostgreSQL database (with pgvector) — point
`DATABASE_URL` at a disposable database before running them; the suite
drops and recreates the schema itself:

```bash
export DATABASE_URL=postgresql+psycopg2://postgres:postgres@localhost:5432/career_agent_test
pytest -v
```

No `OPENAI_API_KEY` and no running Ollama instance are needed to run the
suite -- every test that would otherwise call OpenAI or Ollama mocks the
client (`pytest-mock`'s `mocker` fixture, or a hand-built fake client --
see the `fake_ollama_client` fixture in `tests/conftest.py`) and every
test that would otherwise hit a real URL mocks `requests.get`. Tests never
depend on real network or API calls. PDF-compilation tests are skipped
automatically (`pytest.mark.skipif`) when `pdflatex` isn't on `PATH` --
everything else in the CV/cover-letter pipelines (planning, content
generation, validation, LaTeX rendering/escaping) is still fully tested
either way.

Step 5's tests use a **real** Playwright Chromium browser (this does need
`python3 -m playwright install chromium` done first) against local HTML
fixtures in `tests/fixtures/` loaded via `file://` URLs -- never a real
job site. `tests/conftest.py` forces `BROWSER_HEADLESS=true` for the test
session regardless of your `.env` (so it never pops a visible window
during an automated run) and leaves `DRY_RUN=true` except in the one test
that explicitly proves the explicit-approval submission path works
(`allow_real_submit` fixture, restored afterward). See
`tests/test_browser_application.py` (field mapping / submission gate /
platform detection, no browser needed) and
`tests/test_browser_application_e2e.py` (the full workflow, including
CAPTCHA/login-required detection and both the dry-run-blocks and
explicit-approval-enables submission proofs).

## Project structure

```
career-agent/
├── backend/
│   ├── app/
│   │   ├── main.py               FastAPI app, router registration, logging config
│   │   ├── config.py              Settings (incl. OLLAMA_BASE_URL, OLLAMA_MODEL, COVER_LETTER_*)
│   │   ├── api/                   One router per resource (incl. jobs.py, cvs.py, applications.py)
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
│   │   │   ├── cv_render_service.py        Step 3+4: LaTeX escaping/rendering + pdflatex (shared)
│   │   │   ├── cv_comparison_service.py    Step 3: change tracking + comparison
│   │   │   ├── cover_letter_service.py     Step 4: evidence selection -> Ollama -> validate -> store
│   │   │   ├── application_answer_service.py Step 4: question classification, answers, length limits
│   │   │   ├── answer_validation_service.py  Step 4: deterministic claim validation (shared)
│   │   │   ├── application_material_service.py Step 4: read-only materials package assembly
│   │   │   └── application_service.py     Step 5: DB orchestration for the browser workflow
│   │   ├── browser/                       Step 5: Playwright mechanics
│   │   │   ├── browser_manager.py         Session lifecycle (persistent Chromium context)
│   │   │   ├── page_analyzer.py           CAPTCHA / login-required detection
│   │   │   ├── form_detector.py           Field detection (label/name/id, no fragile selectors)
│   │   │   ├── field_mapper.py            Field -> profile/answer mapping + confidence scoring
│   │   │   ├── form_filler.py             Fills only fields already decided safe to fill
│   │   │   ├── file_uploader.py           Uploads only status=approved CV/cover-letter PDFs
│   │   │   ├── submission_guard.py        The non-negotiable DRY_RUN + approval gate
│   │   │   ├── platform_detector.py       Hostname -> ATS platform -> adapter
│   │   │   └── adapters/
│   │   │       ├── base.py                BaseApplicationAdapter interface
│   │   │       └── generic.py             GenericApplicationAdapter (the only one implemented)
│   │   ├── ai/
│   │   │   ├── client.py          OpenAI client (Steps 2-3) + Ollama client (Step 4), side by side
│   │   │   ├── prompts.py         Step 2 prompts (JOB_ANALYSIS_PROMPT_V1, ...)
│   │   │   ├── structured_outputs.py  Step 2 + Step 4 LLM output schemas
│   │   │   ├── cv_prompts.py       Step 3 prompts (CV_PLAN_PROMPT_V1, ...)
│   │   │   ├── cv_structured_outputs.py  Step 3 LLM output schemas
│   │   │   ├── cover_letter_prompts.py   Step 4 prompts (COVER_LETTER_PROMPT_V1)
│   │   │   └── application_prompts.py    Step 4 prompts (answer generation + shortening)
│   │   ├── scripts/
│   │   │   └── analyze_job.py     Manual end-to-end demo script (Step 2)
│   │   └── db/                    Engine/session, declarative Base
│   ├── alembic/                   Migrations (Steps 1-5, applied in order)
│   ├── tests/                     pytest suite + tests/fixtures/ (local HTML, Step 5 only)
│   ├── requirements.txt
│   ├── pytest.ini
│   └── .env.example
├── cv_templates/
│   ├── ats/ml_engineer.tex        Default ATS-friendly CV LaTeX template
│   ├── cover_letter/standard.tex  Default cover letter LaTeX template
│   └── README.md                  How the template placeholder system works
├── data/
│   ├── career_profile.json        Placeholder seed data
│   ├── test_job_description.txt   Sample job posting for the demo script
│   ├── cvs/                       Generated CV .tex/.pdf output (job_{id}/cv_v{n}.*)
│   ├── application_materials/     Generated cover letter .tex/.pdf output
│   ├── browser_profile/           Persistent Chromium user-data dir (Step 5, gitignored)
│   ├── application_sessions/      Per-application screenshots if enabled (Step 5, gitignored)
│   └── README.md                  How to fill in career_profile.json
├── docs/
│   ├── career-profile-schema.md   Step 1: full schema + verification rules
│   ├── job-matching-schema.md     Step 2: dedup, scoring, match statuses
│   ├── cv-generation.md           Step 3: pipeline, validation, versioning, approval
│   ├── cover-letters-and-applications.md  Step 4: Ollama pipeline, validation, never-guess fields
│   ├── browser-application-assistant.md   Step 5: safety model, field mapping, architecture
│   └── examples/                  Real generated example output for Steps 3-4
└── README.md
```

## What's next (not built yet)

Platform-specific adapters (Greenhouse/Lever/Workday/...) beyond the
generic HTML-form adapter, and outcome tracking after submission
(interview/rejection/offer status). `platform_detector.register_adapter()`
already exists for the former without needing to touch anything else;
`Application.status` and its event log are the exact foundation the
latter would build on.
