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
- **Step 6 — Job-Search Tracking, Analytics & Follow-Up Management**: the
  central source of truth for the whole job search -- status history that's
  never overwritten, a unified timeline, interviews/offers/notes/tags/
  priority, follow-up reminders (never sent automatically), deterministic
  analytics (funnel, conversion rates, response/interview/offer time,
  company/role/skill/source/CV-version performance), a dashboard, and
  CSV/JSON export. Every metric is a plain SQL/Python calculation -- no
  LLM involved. See
  [`docs/job-search-tracking.md`](docs/job-search-tracking.md).
- **Step 7 — Job Search Intelligence & Recommendations**: learns from
  your historical activity to recommend which jobs to prioritize, which
  skills to close gaps in, which CV/source/role has performed best, and
  why rejections might be happening -- every recommendation carries a
  WHAT + WHY + EVIDENCE + CONFIDENCE, and the user decides whether to
  accept, dismiss, or complete it. Scoring is deterministic; the local
  Ollama model is only used to explain already-computed evidence (with
  output validation that discards any unsupported statistic) and to
  generate interview prep questions/draft answers grounded only in your
  verified Career Profile. See
  [`docs/job-search-intelligence.md`](docs/job-search-intelligence.md).

- **Step 8 — Job Discovery**: searches public, ToS-compliant job sources
  (Greenhouse and Lever company boards, RemoteOK, We Work Remotely,
  Adzuna, USAJobs) using your target roles/locations/companies, and
  stores new matches through the same dedup-aware path as a manually
  pasted-in job. Deliberately does **not** scrape LinkedIn or Indeed --
  both explicitly prohibit automated access in their ToS and run active
  anti-bot enforcement (LinkedIn has litigated and won against scrapers
  before). Those two stay a manual paste/URL flow, same as Step 2. Runs
  on-demand (`POST /discovery/run`) or on an optional background
  interval (`DISCOVERY_SCHEDULER_ENABLED=true`), never both silently --
  discovery only ever runs when you ask it to, or when you've explicitly
  opted into the scheduler.

This is an assisted workflow, not an autonomous agent -- nothing is ever
submitted, or changed in your Career Profile, without a human deciding
to do so first.

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
DEFAULT_FOLLOWUP_DAYS=7
TIMEZONE=UTC
DISCOVERY_ENABLED_SOURCES=["greenhouse","lever","remoteok","weworkremotely","adzuna","usajobs"]
DISCOVERY_MAX_RESULTS_PER_SOURCE=25
ADZUNA_APP_ID=
ADZUNA_APP_KEY=
ADZUNA_COUNTRY=us
USAJOBS_API_KEY=
USAJOBS_USER_AGENT_EMAIL=
DISCOVERY_SCHEDULER_ENABLED=false
DISCOVERY_SCHEDULER_INTERVAL_HOURS=24
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
within/around that range). `DEFAULT_FOLLOWUP_DAYS` (Step 6) is only used
to compute a *suggested* follow-up date -- nothing is scheduled or sent
automatically. `DISCOVERY_ENABLED_SOURCES` (Step 8) controls which
sources `POST /discovery/run` searches by default (a request can still
override it with its own `sources` list); Greenhouse/Lever/RemoteOK/We
Work Remotely need no key, so leaving `ADZUNA_APP_ID`/`ADZUNA_APP_KEY`
or `USAJOBS_API_KEY`/`USAJOBS_USER_AGENT_EMAIL` blank just means those
two sources report a configuration error in the run's results rather
than searching -- register free keys at
[developer.adzuna.com](https://developer.adzuna.com/) and
[developer.usajobs.gov](https://developer.usajobs.gov/) to enable them.
`DISCOVERY_SCHEDULER_ENABLED` is a separate opt-in for running discovery
automatically on `DISCOVERY_SCHEDULER_INTERVAL_HOURS` -- discovery
always works on-demand regardless of this setting.

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

## 7f. Step 6: job-search tracking, analytics, and follow-up management

The dashboard -- everything at a glance:

```bash
curl http://localhost:8000/dashboard | python3 -m json.tool
```

Search and filter jobs/applications (used by search/filter/sort spec
tests; supports company, role, status, priority, tag, source, match
score, deadline, location, remote, date, and `sort=newest|oldest|
highest_match|lowest_match|deadline|priority|latest_status_change`):

```bash
curl "http://localhost:8000/jobs/search?status=shortlisted&sort=deadline"
curl "http://localhost:8000/applications/search?min_match_score=80&sort=priority"
```

Manually move an application forward -- every change is recorded, never
overwritten:

```bash
curl -X PATCH http://localhost:8000/applications/1/status \
  -H "Content-Type: application/json" \
  -d '{"status": "interview", "reason": "Recruiter scheduled a technical interview"}'

curl http://localhost:8000/applications/1/status-history
curl http://localhost:8000/applications/1/timeline | python3 -m json.tool
```

Record an interview, an offer, a follow-up, and a note:

```bash
curl -X POST http://localhost:8000/applications/1/interviews \
  -H "Content-Type: application/json" \
  -d '{"type": "technical", "scheduled_at": "2026-08-20T15:00:00Z", "interviewer": "Jane Doe"}'

curl -X POST http://localhost:8000/applications/1/offers \
  -H "Content-Type: application/json" \
  -d '{"company": "Example Company", "role": "ML Engineer", "salary": 140000, "currency": "USD"}'

curl http://localhost:8000/applications/1/followups/suggested
curl -X POST http://localhost:8000/applications/1/followups \
  -H "Content-Type: application/json" -d '{"due_date": "2026-08-22", "subject": "Thank the interviewer"}'

curl -X POST http://localhost:8000/applications/1/notes \
  -H "Content-Type: application/json" -d '{"content": "Recruiter is John.", "note_type": "recruiter"}'
```

Tags, priority, and archiving (never deletes):

```bash
curl -X PATCH http://localhost:8000/jobs/1/tags -H "Content-Type: application/json" -d '{"tags": ["dream-company", "ML"]}'
curl -X PATCH http://localhost:8000/applications/1/priority -H "Content-Type: application/json" -d '{"priority": "high"}'
curl -X POST http://localhost:8000/applications/1/archive
```

Analytics -- every number is a plain SQL/Python calculation, formulas
documented in `docs/job-search-tracking.md`:

```bash
curl http://localhost:8000/analytics/overview | python3 -m json.tool     # funnel, conversion rates, time-to-X, velocity
curl http://localhost:8000/analytics/companies
curl http://localhost:8000/analytics/skills                              # demand + potential skill gaps
curl http://localhost:8000/analytics/match-scores
curl http://localhost:8000/analytics/cv-versions
curl http://localhost:8000/analytics/weekly
```

What's coming up, and export:

```bash
curl http://localhost:8000/notifications/upcoming
curl http://localhost:8000/calendar/upcoming
curl "http://localhost:8000/applications/export?format=csv" -o applications.csv
```

Back up the database locally:

```bash
python -m app.cli backup
```

Full Step 6 endpoint list: `GET /dashboard`, `GET /jobs/search`,
`POST /jobs/{id}/archive`, `PATCH /jobs/{id}/status`,
`PATCH /jobs/{id}/tags`, `PATCH /jobs/{id}/priority`,
`GET /jobs/{id}/duplicates`, `POST/GET /jobs/{id}/notes`,
`GET /applications/search`, `GET /applications/export`,
`GET /applications/{id}/timeline`, `GET /applications/{id}/readiness`,
`GET /applications/{id}/interview-context`,
`PATCH /applications/{id}/status`,
`GET /applications/{id}/status-history`,
`POST /applications/{id}/events`, `POST /applications/{id}/archive`,
`PATCH /applications/{id}/tags`, `PATCH /applications/{id}/priority`,
`POST/GET /applications/{id}/interviews`,
`PATCH /applications/{id}/interviews/{id}`,
`GET /applications/{id}/followups/suggested`,
`POST/GET /applications/{id}/followups`, `PATCH /followups/{id}`,
`POST/GET /applications/{id}/offers`,
`PATCH /applications/{id}/offers/{id}`,
`POST/GET /applications/{id}/notes`, `GET /notifications/upcoming`,
`GET /calendar/upcoming`, `GET /analytics/overview`,
`GET /analytics/status`, `GET /analytics/companies`,
`GET /analytics/roles`, `GET /analytics/skills`,
`GET /analytics/sources`, `GET /analytics/match-scores`,
`GET /analytics/cv-versions`, `GET /analytics/weekly`,
`GET /analytics/monthly`.

See `docs/job-search-tracking.md` for the full schema, analytics
formulas, and design rationale (including two real bugs the Step 6 test
suite caught: `compute_match()` silently regressing an already-advanced
job's status, and CV/cover-letter analytics silently collapsing rows that
happen to share the same version name).

## 7g. Step 7: job search intelligence & recommendations

Generate recommendations from your current history, then review, accept,
or dismiss them:

```bash
curl -X POST http://localhost:8000/intelligence/recommendations/generate | python3 -m json.tool
curl http://localhost:8000/intelligence/recommendations
curl -X POST http://localhost:8000/intelligence/recommendations/1/accept
```

Every recommendation carries its own reasoning -- nothing is ever
unexplained:

```json
{
  "type": "job_priority",
  "title": "Prioritize: Machine Learning Engineer at Example Company",
  "description": "Priority 92/100. Match score: 94% Required skill coverage: 92% Matches your target role 'ML Engineer'.",
  "confidence": 0.83,
  "confidence_reason": "Based on 32 historical data points.",
  "evidence": {"score": 92, "factors": {"match_score": 0.94, "required_skill_coverage": 0.92}},
  "action": "Review tailored CV and prepare application."
}
```

Per-job and per-application intelligence (priority score, opportunity
score, CV gap analysis, interview-prep context, all with reasons):

```bash
curl http://localhost:8000/intelligence/jobs/1 | python3 -m json.tool
curl http://localhost:8000/intelligence/applications/1 | python3 -m json.tool
```

Skill demand and gaps across every analyzed job -- never a claim that
you "need" a skill, only that it's frequently requested:

```bash
curl http://localhost:8000/intelligence/skills/gaps | python3 -m json.tool
curl http://localhost:8000/intelligence/skills/demand
```

Career-level view, weekly review, and personalized strategy:

```bash
curl http://localhost:8000/intelligence/career | python3 -m json.tool
curl http://localhost:8000/intelligence/weekly-review | python3 -m json.tool
curl http://localhost:8000/intelligence/strategy | python3 -m json.tool
```

Configure your own job-search goals (never assumed) and track progress
against them (never phrased as a failure):

```bash
curl -X PUT http://localhost:8000/intelligence/goals \
  -H "Content-Type: application/json" \
  -d '{"applications_per_week": 10, "interviews_per_month": 3}'
curl http://localhost:8000/intelligence/goals/progress
```

Interview preparation -- questions and draft answers, both grounded only
in the actual job description and your verified Career Profile (requires
`OLLAMA_MODEL`, same as Step 4):

```bash
curl -X POST http://localhost:8000/interview-prep/questions \
  -H "Content-Type: application/json" -d '{"application_id": 1}' | python3 -m json.tool

curl -X POST http://localhost:8000/interview-prep/answer \
  -H "Content-Type: application/json" \
  -d '{"application_id": 1, "question": "Tell me about a challenging project.", "star": true}'
```

Record why an application was rejected (only ever set by you -- never
inferred):

```bash
curl -X PATCH http://localhost:8000/applications/1/rejection-reason \
  -H "Content-Type: application/json" -d '{"rejection_reason": "skills_gap"}'
```

Full Step 7 endpoint list: `GET/POST /intelligence/recommendations*`,
`GET /intelligence/jobs/{id}`, `GET /intelligence/applications/{id}`,
`GET /intelligence/skills`, `GET /intelligence/skills/gaps`,
`GET /intelligence/skills/demand`, `GET /intelligence/career`,
`GET /intelligence/weekly-review`, `GET /intelligence/strategy`,
`GET /intelligence/applications/{id}/interview-preparation`,
`GET/PUT /intelligence/goals`, `GET /intelligence/goals/progress`,
`POST /interview-prep/questions`, `POST /interview-prep/answer`,
`PATCH /applications/{id}/rejection-reason`.

See `docs/job-search-intelligence.md` for the priority-score formula,
skill-gap ranking formula, confidence system, and exactly how LLM output
is validated before it's ever shown to you.

## 7h. Step 8: job discovery

Discovery searches use your target roles/locations (career profile or
job-search goal, goal takes priority if set) and, for Greenhouse/Lever,
your goal's `target_companies` as board tokens -- set those first if you
want those two sources to find anything:

```bash
curl -X PUT http://localhost:8000/intelligence/goals \
  -H "Content-Type: application/json" \
  -d '{"target_roles": ["Machine Learning Engineer"], "target_locations": ["Remote"], "target_companies": ["stripe", "airbnb"]}'
```

Run discovery now, across every configured source:

```bash
curl -X POST http://localhost:8000/discovery/run | python3 -m json.tool
```

Override the query for a single run without touching the stored goal, or
search only specific sources:

```bash
curl -X POST http://localhost:8000/discovery/run \
  -H "Content-Type: application/json" \
  -d '{"sources": ["remoteok", "weworkremotely"], "keywords": ["Computer Vision Engineer"], "locations": ["Remote"]}'
```

Every run is logged, with a per-source breakdown (found/created/
duplicate/error) -- a source erroring (e.g. Adzuna without a key
configured) never stops the others from running:

```json
{
  "id": 1, "trigger": "manual", "jobs_found": 50, "jobs_created": 50,
  "results": {
    "greenhouse": {"found": 0, "created": 0, "duplicate": 0, "error": null, "note": "No target companies configured..."},
    "remoteok": {"found": 25, "created": 25, "duplicate": 0, "error": null},
    "adzuna": {"found": 0, "created": 0, "duplicate": 0, "error": "Adzuna is not configured -- set ADZUNA_APP_ID and ADZUNA_APP_KEY."}
  }
}
```

Review run history, and what each source needs to be usable:

```bash
curl http://localhost:8000/discovery/runs
curl http://localhost:8000/discovery/runs/1
curl http://localhost:8000/discovery/sources
```

Jobs found this way land as ordinary `discovered`-status Job rows --
`POST /jobs/{id}/analyze` and `POST /jobs/{id}/match` (Step 2) work on
them exactly as they do on a manually pasted-in job, since discovery
already filled in title/company/location/salary/etc directly from the
source (no AI extraction needed just to know those).

Full Step 8 endpoint list: `POST /discovery/run`, `GET /discovery/runs`,
`GET /discovery/runs/{id}`, `GET /discovery/sources`.

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

`tests/test_tracking.py` covers Step 6 against a synthetic dataset (20
jobs, 10 shortlisted, 8 applications, 3 responses, 2 interviews, 1 offer
-- entirely fake companies/data) verified against hand-computed expected
values: status history, timeline, follow-ups, interviews, offers, notes,
tags, priority, duplicate detection, deadline handling, every analytics
formula, readiness, CSV/JSON export, archiving, search/filter/sort,
timezone-awareness, and cascading deletes (no orphaned rows).
`tests/test_intelligence.py` covers Step 7 against a synthetic dataset
(50 jobs, 30 shortlisted, 25 applications, 8 responses, 5 interviews, 2
offers, 3 CV versions, 4 sources, 5 roles, a real AWS skill gap, 6
rejections with varying reasons) across all 20 categories from spec
section 62, including a direct test that the LLM output validator strips
a fabricated statistic and that an interview answer claiming an
unsupported skill is flagged rather than silently served.

`tests/test_end_to_end.py` drives the complete Step 1 → Step 7 workflow
through the real API in one pass -- profile, job analysis/match, tailored
CV, cover letter + answers, a real (mocked-AI, real-Playwright) Step 5
submission, Step 6 tracking through to an `interview` status with a
pending follow-up, and Step 7 intelligence (priority/opportunity scoring,
recommendation generation + acceptance, weekly review, career strategy)
-- printing the same "AI JOB SEARCH INTELLIGENCE" summary shape as spec
section 64's example. This test is what originally caught two real bugs
(now fixed and covered by regression tests): `compute_match()` silently
regressing an already-shortlisted job's status back to `matched`, and
`POST /applications/{id}/cancel` overwriting a just-confirmed `submitted`
status with `abandoned` (fixed by not calling `/cancel` after a
successful submission -- see `docs/job-search-tracking.md`).

`tests/test_discovery.py` covers Step 8: each source adapter's parsing
against realistic mocked HTTP responses (never real network calls) --
including Greenhouse/Lever's 404-means-not-on-this-ATS handling, Adzuna/
USAJobs raising a clear configuration error when their keys aren't set,
and RemoteOK's feed's own legal-notice first element being skipped
correctly -- the dedup-aware ingest path (by external id, then by
canonical URL/description hash, matching an already-known job even
across sources), orchestration's per-source error isolation (one source
failing never blocks the others), goal-over-profile query precedence,
and the API endpoints.

## 9. Frontend

A React dashboard covering Step 6 (analytics) and Step 7 (recommendations,
job/application intelligence) -- built with Vite, TypeScript, Tailwind
CSS, React Router, and Recharts. It never talks to any AI provider
directly; it only calls this backend's REST API.

```bash
cd career-agent/frontend
npm install
npm run dev
```

Opens at `http://localhost:5173`. Run the backend separately
(`uvicorn app.main:app --reload` from `career-agent/backend`, per section
5) -- the Vite dev server proxies any `/api/*` request to
`http://localhost:8000` (see `vite.config.ts`), so the frontend and
backend are same-origin in dev and CORS never comes into play for the
normal workflow. `CORSMiddleware` is still enabled on the backend
(`frontend_origins` in `app/config.py`, defaulting to the Vite dev server
ports) as a fallback for calling the API directly from the browser
outside the proxy.

> **Vite version note:** `npm create vite@latest` currently defaults to
> an experimental Vite 8 build using the Rolldown bundler, which doesn't
> ship a native binding for every platform/Node combination.
> `package.json` pins the stable `vite@^6` / `@vitejs/plugin-react@^4`
> toolchain instead -- if you regenerate `package.json` from scratch,
> pin the same way rather than fighting the experimental bundler.

Pages:

- **Dashboard** (`/`) -- the Step 6 funnel, conversion rates, time-to-X
  stats, and upcoming interviews/follow-ups/deadlines, all from
  `GET /dashboard`.
- **Discovery** (`/discovery`) -- the Step 8 job discovery run trigger,
  per-source status/configuration, and run history with a per-source
  found/created/duplicate/error breakdown.
- **Recommendations** (`/recommendations`) -- the Step 7 recommendation
  feed with type/priority/status filters, confidence bars, evidence
  detail, and accept/dismiss/complete actions.
- **Jobs** (`/jobs`, `/jobs/:id`) -- search/filter/sort over
  `GET /jobs/search`, and a detail view with the Step 7 priority score,
  opportunity score, requirement match breakdown, and CV recommendations
  (`GET /intelligence/jobs/{id}`).
- **Applications** (`/applications`, `/applications/:id`) -- search/
  filter/sort, and a detail view with readiness checks, status updates,
  timeline, interviews, offers, interview-prep context, and notes
  (`GET /intelligence/applications/{id}` plus the Step 6 tracking
  endpoints).

`npm run build` produces a static production build in `dist/`; nothing
currently serves it automatically (there's no reverse proxy or static
file mount in the FastAPI app) -- `npm run dev` is the supported way to
run the frontend today.

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
│   │   │   ├── application_service.py     Step 5: DB orchestration for the browser workflow
│   │   │   ├── tracking_service.py        Step 6: status history, timeline, readiness, snapshot, duplicates
│   │   │   ├── followup_service.py        Step 6: follow-up reminders (suggested only, never sent)
│   │   │   ├── interview_service.py       Step 6: interview CRUD
│   │   │   ├── offer_service.py           Step 6: offer CRUD
│   │   │   ├── note_service.py            Step 6: application/job notes
│   │   │   ├── analytics_service.py       Step 6: funnel, conversion rates, all analytics (SQL/Python only)
│   │   │   ├── export_service.py          Step 6: CSV/JSON application export
│   │   │   ├── recommendation_engine.py   Step 7: the only writer of Recommendation rows
│   │   │   ├── goal_service.py            Step 7: UserJobSearchGoal CRUD + progress comparison
│   │   │   └── discovery_service.py       Step 8: builds the search query, runs each source, logs a DiscoveryRun
│   │   ├── cli.py                         Step 6: `python -m app.cli backup`
│   │   ├── intelligence/                  Step 7: deterministic analyzers (no LLM except explainer/interview_analyzer)
│   │   │   ├── confidence.py              Small-sample-protected confidence scoring
│   │   │   ├── job_prioritizer.py         Priority score + opportunity score
│   │   │   ├── skill_gap_analyzer.py      Demand/gap ranking (frequency x importance x relevance)
│   │   │   ├── cv_analyzer.py             Profile-vs-CV and job-vs-CV gap analysis, keyword coverage
│   │   │   ├── rejection_analyzer.py      Rejection pattern analysis
│   │   │   ├── career_insights.py         Company/source/role strategy, career direction, weekly review
│   │   │   ├── application_analyzer.py    Per-job/per-application intelligence assembly
│   │   │   ├── interview_analyzer.py      Interview prep context/output + question/answer generation
│   │   │   └── recommendation_explainer.py  LLM explanation layer + output validation
│   │   ├── discovery/                     Step 8: one adapter per public job source, no LLM involved
│   │   │   ├── base.py                    DiscoveredJob/DiscoveryQuery + DiscoverySourceError
│   │   │   ├── matching.py                Keyword matching + Greenhouse/Lever board-token guessing
│   │   │   ├── greenhouse.py              Per-company board API (no key)
│   │   │   ├── lever.py                   Per-company board API (no key)
│   │   │   ├── remoteok.py                Global feed API (no key)
│   │   │   ├── weworkremotely.py          Global RSS feed (no key)
│   │   │   ├── adzuna.py                  Keyword+location search API (free key)
│   │   │   └── usajobs.py                 Keyword+location search API (free key)
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
│   │   │   ├── application_prompts.py    Step 4 prompts (answer generation + shortening)
│   │   │   ├── interview_prep_prompts.py    Step 7 prompts (questions + draft answers)
│   │   │   ├── interview_prep_outputs.py    Step 7 LLM output schemas
│   │   │   ├── recommendation_prompts.py    Step 7 prompt (evidence -> explanation)
│   │   │   └── recommendation_outputs.py    Step 7 LLM output schema
│   │   ├── scripts/
│   │   │   └── analyze_job.py     Manual end-to-end demo script (Step 2)
│   │   └── db/                    Engine/session, declarative Base
│   ├── alembic/                   Migrations (Steps 1-8, applied in order)
│   ├── tests/                     pytest suite + tests/fixtures/ (local HTML, Step 5 only)
│   ├── requirements.txt
│   ├── pytest.ini
│   └── .env.example
├── frontend/
│   ├── src/
│   │   ├── main.tsx                Router setup (BrowserRouter + routes)
│   │   ├── App.tsx                 Layout shell (sidebar nav + <Outlet />)
│   │   ├── api/                    Typed client: client.ts, types.ts, one file per resource
│   │   ├── hooks/useApi.ts         Fetch/loading/error/refetch hook
│   │   ├── components/             Card, StatCard, Badge/StatusBadge, Button, ConfidenceBar, AsyncState
│   │   └── pages/                  DashboardPage, DiscoveryPage, RecommendationsPage, Jobs*Page, Applications*Page
│   ├── vite.config.ts              Dev-server proxy: /api -> http://localhost:8000
│   └── package.json
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
│   ├── backups/                   `python -m app.cli backup` output (Step 6, gitignored)
│   └── README.md                  How to fill in career_profile.json
├── docs/
│   ├── career-profile-schema.md   Step 1: full schema + verification rules
│   ├── job-matching-schema.md     Step 2: dedup, scoring, match statuses
│   ├── cv-generation.md           Step 3: pipeline, validation, versioning, approval
│   ├── cover-letters-and-applications.md  Step 4: Ollama pipeline, validation, never-guess fields
│   ├── browser-application-assistant.md   Step 5: safety model, field mapping, architecture
│   ├── job-search-tracking.md     Step 6: schema, analytics formulas, design rationale
│   ├── job-search-intelligence.md Step 7: priority/skill-gap formulas, confidence, LLM validation
│   └── examples/                  Real generated example output for Steps 3-4
└── README.md
```

## What's next (not built yet)

Platform-specific adapters (Greenhouse/Lever/Workday/...) beyond the
generic HTML-form adapter -- `platform_detector.register_adapter()`
already exists for this without needing to touch anything else. External
notifications (email/calendar/push) beyond the current read-only
`GET /notifications/upcoming` / `GET /calendar/upcoming`. Recommendation
feedback (accept/dismiss/complete) is stored but not yet used to actually
tune future ranking -- `recommendation_engine.py` is the natural place a
future step would add that. LinkedIn and Indeed are deliberately never
scraped by Step 8 (see `app/discovery/base.py`) -- jobs from either stay
a manual paste/URL flow through Step 2. Greenhouse/Lever discovery only
searches companies you've explicitly listed in your job-search goal's
`target_companies` -- there's no cross-company search API for either, by
design on their end, not a gap in this implementation.
