# Career Agent

An AI-powered job application agent, built step by step.

- **Step 1 — Career Profile & Knowledge Base**: a structured, verified
  store of your career facts (education, experience, projects, skills,
  research, certifications, achievements) with an evidence system that
  prevents any future AI layer from inventing experience you don't have.
  See [`docs/career-profile-schema.md`](docs/career-profile-schema.md).
- **Step 1b — Resume Upload (Profile Parser)**: upload a PDF/text resume
  and AI extracts skills/experience/education/projects/etc into the
  shape above -- but nothing is written until you explicitly confirm it,
  and everything confirmed lands `verified: false` regardless of what
  the AI extracted, exactly like every other AI-touched fact in this
  system.
- **Step 2 — Job Ingestion, Analysis & Matching**: paste a job URL or
  description in, get a deterministic, explainable fit score out. See
  [`docs/job-matching-schema.md`](docs/job-matching-schema.md).
- **Step 2b — Job Discovery**: searches public, ToS-compliant job sources
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
- **Step 8 — AI Job Search Agent / Orchestrator**: connects everything
  above into one controllable agent -- give it a high-level goal
  ("Find 10 ML Engineer jobs in Islamabad or remote", "Prepare the top
  3 applications") and it plans and executes the right sequence of the
  *existing* tools above to get there. It never reimplements Steps 1-7,
  never submits an application or sends an external message without
  your explicit approval, and stops cleanly (never runs away) at every
  point a real decision is needed. See the "Step 8" section below.

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
AGENT_ENABLED=true
MAX_AGENT_STEPS=20
MAX_AGENT_RETRIES=2
AUTO_GENERATE_MATERIALS=true
AUTO_PREPARE_APPLICATIONS=true
AUTO_SUBMIT_APPLICATIONS=false
AUTO_SEND_MESSAGES=false
REQUIRE_APPROVAL_FOR_EXTERNAL_ACTIONS=true
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
automatically. `DISCOVERY_ENABLED_SOURCES` (Step 2b) controls which
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
always works on-demand regardless of this setting. `MAX_AGENT_STEPS`
(Step 8) is how many plan steps a single `POST /agent/chat` or
`/resume` call executes before pausing (never failing) so it can be
resumed; `MAX_AGENT_RETRIES` limits retries of a *failed* step and never
applies to `application.submit`/`application.approve_submission`
regardless of its value. The `AUTO_*`/`REQUIRE_APPROVAL_FOR_EXTERNAL_
ACTIONS` flags describe the agent's conservative default posture
(materials generation and application prep run on their own; submission
and external messages never do) rather than being read directly by
individual tools -- the actual, non-overridable gate is
`permissions.py`'s risk policy, reusing Step 5's own `DRY_RUN` as the
hard stop underneath `application.submit` rather than adding a second
one.

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

## 7a. Step 1b: resume upload (Profile Parser)

Upload a resume (PDF or plain text) -- this only ever creates a
`ResumeImport` row for you to review; nothing touches the Career Profile
yet:

```bash
curl -X POST http://localhost:8000/profile/resume/upload -F "file=@resume.pdf" | python3 -m json.tool
```

Review what was extracted, then confirm (writes everything as
`verified: false`, attaching to your existing profile if you have one,
or creating a new one if the resume had a name/email/title and you
don't) or reject (discards it, nothing written):

```bash
curl http://localhost:8000/profile/resume/imports/1 | python3 -m json.tool
curl -X POST http://localhost:8000/profile/resume/imports/1/confirm
curl -X POST http://localhost:8000/profile/resume/imports/1/reject
```

Requires `OPENAI_API_KEY` (same extraction pipeline pattern as Step 2's
job analysis). Only `.pdf`, `.txt`, and `.md` are supported -- other
formats are rejected with a clear error before any AI call happens.
Full endpoint list: `POST /profile/resume/upload`,
`GET /profile/resume/imports`, `GET /profile/resume/imports/{id}`,
`POST /profile/resume/imports/{id}/confirm`,
`POST /profile/resume/imports/{id}/reject`.

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

## 7h. Step 2b: job discovery

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

Full Step 2b endpoint list: `POST /discovery/run`, `GET /discovery/runs`,
`GET /discovery/runs/{id}`, `GET /discovery/sources`.

### Running persistently on macOS (survives reboots)

`DISCOVERY_SCHEDULER_ENABLED=true` only fires while the `uvicorn`
process is alive -- there's no separate daemon. To keep it running
across logins/reboots on macOS without a terminal window open, run the
backend as a per-user `launchd` LaunchAgent (no `sudo`/root daemon
needed):

```bash
cp launchd/com.jobiest.career-agent-backend.plist.example \
   ~/Library/LaunchAgents/com.jobiest.career-agent-backend.plist
```

Edit the copied file and replace every `/ABSOLUTE/PATH/TO/...`
placeholder with your actual paths (the repo's `career-agent/backend`
directory, and your home directory for the log files), then load it:

```bash
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.jobiest.career-agent-backend.plist
```

It starts immediately and again on every future login; `KeepAlive`
restarts it automatically if it ever crashes. Useful commands:

```bash
launchctl print gui/$(id -u)/com.jobiest.career-agent-backend   # status, pid, paths
launchctl kickstart -k gui/$(id -u)/com.jobiest.career-agent-backend   # restart (e.g. after a code change)
launchctl bootout gui/$(id -u)/com.jobiest.career-agent-backend   # stop and unload
```

Logs go to `StandardOutPath`/`StandardErrorPath` in the plist (the
`.err.log` file is where uvicorn's own INFO logs land, not just errors).
Notes:

- This starts at **login**, not at raw boot before anyone logs in --
  the normal scope for a per-user LaunchAgent. Enable auto-login if you
  want it up before you're at the keyboard.
- The plist doesn't pass `--reload`, since a hot-reloading process tree
  doesn't fit launchd's supervision model well -- after editing backend
  code, restart with `launchctl kickstart -k ...` above.
- Once loaded, this owns port 8000. Don't also run a manual
  `uvicorn --port 8000` alongside it -- use a different port for that if
  you need a separate hot-reloading instance while developing.

## 7i. Step 8: AI job search agent / orchestrator

Give it one high-level request instead of calling Steps 1-7's endpoints
yourself, one at a time:

```bash
curl -X POST http://localhost:8000/agent/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Find 5 strong ML Engineer jobs"}' | python3 -m json.tool
```

```json
{
  "id": 1, "status": "completed",
  "objective": "Find and rank jobs matching the request.",
  "final_result": {
    "completed": ["discover_new_jobs", "search_jobs", "rank_jobs"],
    "job_ids": [12, 8, 41, 3, 19],
    "summary": "OBJECTIVE: Find and rank jobs matching the request.\n\nCOMPLETED:\n  ✓ discover_new_jobs\n  ✓ search_jobs\n  ✓ rank_jobs\n\nAPPROVAL REQUIRED:\n  (none)"
  }
}
```

"Find jobs" actually finds some: `discover_new_jobs` runs Step 2b
first (dedup-aware, so this is safe to do on every search), *then*
`search_jobs` looks across the now-current database. `rank_jobs` skips
anything below a 70% deterministic match score by default (your Step 7
goal's `minimum_match_score` overrides this if you've set one) -- a weak
match never reaches `cv.generate`.

A request that implies real, persistent actions (preparing applications)
still runs on its own -- generating a CV/cover letter and creating an
`Application` row aren't submission, so nothing stops it:

```bash
curl -X POST http://localhost:8000/agent/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Find 3 strong ML jobs and prepare applications"}'
```

"Submit application 42" drives the *entire* browser sequence itself --
open the browser, detect CAPTCHA/login, fill known-safe fields, review,
then stop for approval right before the one irreversible click:

```bash
curl -X POST http://localhost:8000/agent/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Submit application 42"}'
# {"status": "waiting_for_approval", ...}   -- start/analyze/fill/review all ran already

curl http://localhost:8000/agent/tasks/2/approvals
# [{"id": 7, "status": "pending", "description": "Approve: submit_1 (application.submit)", ...}]

curl -X POST http://localhost:8000/agent/approvals/7/approve
# approving immediately resumes the task -- no separate /resume call needed
```

If a CAPTCHA or login page is detected, or a field like salary needs a
human answer, the task pauses at `waiting_for_user_input` instead --
with a clear message telling you exactly what to do (solve it in the
browser window, or `POST /applications/{id}/fields/{field_id}/input`)
and `POST /agent/tasks/{id}/resume` once you have:

```bash
curl http://localhost:8000/agent/tasks/2/events | python3 -c "import json,sys; [print(e['message']) for e in json.load(sys.stdin)]"
# ...
# 3 field(s) need your input before this application can continue: Expected Salary. Answer each via POST /applications/42/fields/{field_id}/input ...

curl -X POST http://localhost:8000/applications/42/fields/10/input -d '{"value": "$140,000"}'
curl -X POST http://localhost:8000/agent/tasks/2/resume
```

Rejecting instead just skips that step and the task still completes
cleanly (spec-equivalent: "continue only with what was approved"):

```bash
curl -X POST http://localhost:8000/agent/approvals/7/reject
```

A follow-up like "prepare the top 3" resolves against an earlier task's
own result -- never guessed, always an explicit reference you provide:

```bash
curl -X POST http://localhost:8000/agent/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Prepare the top 3", "previous_task_id": 1}'
```

Inspect or control a task at any point:

```bash
curl http://localhost:8000/agent/tasks/1                # status, objective, final_result
curl http://localhost:8000/agent/tasks/1/plan            # every step, in order, with its result
curl http://localhost:8000/agent/tasks/1/events          # the full execution log
curl -X POST http://localhost:8000/agent/tasks/1/pause
curl -X POST http://localhost:8000/agent/tasks/1/resume
curl -X POST http://localhost:8000/agent/tasks/1/cancel  # also closes any browser session it opened
curl http://localhost:8000/agent/usage                   # tool-call counts, execution time, LLM-planning calls
```

Or from the command line -- every subcommand runs through the exact same
`handle_chat_message()` path as `POST /agent/chat`, so the CLI and API
can never drift apart:

```bash
python -m app.agent search           # "Find jobs matching my profile"
python -m app.agent prepare          # "Prepare the top 5 applications"
python -m app.agent review           # "Review my applications"
python -m app.agent weekly-review
python -m app.agent status
python -m app.agent interview --application-id 42
```

### Architecture

```
User request
  -> Intent detection (deterministic regex first; local Ollama only for
     genuinely ambiguous phrasing, and only to CLASSIFY into one of a
     fixed set of known intents + extract a count/location/id -- never
     to write a tool name or argument itself)
  -> Planning (hand-written templates turn the intent into an ordered
     AgentPlanStep list, one real tool call per step)
  -> Execution, one step at a time (app/agent/executor.py)
       -> requires_approval? create an AgentApproval, stop cleanly
       -> otherwise: validate arguments against the tool's schema,
          call its handler (a thin wrapper over an existing Steps-1-7
          service/router function), log the result
       -> MAX_AGENT_STEPS reached? pause cleanly, resumable later
  -> Final structured result (OBJECTIVE / COMPLETED / PENDING /
     APPROVAL REQUIRED / WARNINGS) stored on the task
```

`backend/app/agent/`:

- **tool_registry.py** / **tools/*.py** -- ~46 tools, one thin wrapper
  per Steps-1-7 capability (`jobs.search`, `cv.generate`,
  `application.submit`, `intelligence.recommendations`, ...). Each
  declares a pydantic input schema, a permission (`read_only` / `write`
  / `external_action`), and a risk level (`low` / `medium` / `high`).
  A handful are genuinely new *composition* (not reimplementation):
  `jobs.rank` analyzes+matches+ranks a batch of jobs by calling the same
  functions `jobs.analyze`/`jobs.match` do, in a loop; `application.
  prepare_batch` does the same for generating materials + creating
  applications across several jobs in one call, since the job count
  isn't known until the search/rank step actually runs.
- **tool_router.py** -- the only path from a plan step to a real
  service call: validates arguments against the tool's schema, invokes
  it, normalizes the result into `{success, data, warnings, errors}`.
- **planner.py** -- deterministic intent regexes covering every example
  command in the spec this step was built from, a local-LLM fallback for
  ambiguous phrasing (classification only, see `prompts.py`), and one
  hand-written plan-template function per intent.
- **executor.py** -- the controlled loop: `$PREV_JOB_IDS`/
  `$PREV_RANKED_JOB_IDS` placeholder resolution between steps, approval
  gating, `MAX_AGENT_STEPS`, limited retries (never for
  `application.submit`/`application.approve_submission` -- spec: never
  blindly retry an irreversible action), and the final structured-result
  builder.
- **permissions.py** -- the approval policy: LOW always auto-runs,
  MEDIUM auto-runs unless the tool is in `ALWAYS_REQUIRES_APPROVAL`
  (submission, external messages, profile/goal changes, offer
  acceptance), HIGH always requires approval with no override -- a
  plan step's own `requires_approval` flag can only strengthen this,
  never weaken it.
- **approval_manager.py** -- the approval lifecycle (request / approve /
  reject / expire); nothing except an explicit
  `POST /agent/approvals/{id}/approve|reject` ever changes an approval's
  status -- conversational text like "okay" or "looks good" is never
  interpreted as consent.
- **task_manager.py** -- the DB access layer for `AgentTask`/
  `AgentPlanStep`/`AgentEvent`/`AgentApproval` (append-only event log,
  like Step 5's `ApplicationEvent`).
- **memory.py** -- resolves conversational follow-ups ("the top 3")
  against a previous task's own stored result; never a second copy of
  the Career Profile or of conversation history (spec: don't duplicate
  what Steps 1-7 already store).
- **validators.py** -- pre-flight plan validation (every referenced
  tool must exist) and `wrap_untrusted_text()`, which marks external
  content (job descriptions, scraped pages) as DATA before it reaches
  an LLM prompt and flags obvious injection phrasing inline. The real
  guarantee against prompt injection is structural, not textual: the
  LLM can only ever *name* one of the ~44 registered tools, and every
  argument is schema-validated before a handler runs -- there is no
  code path from "text an LLM produced" to executing arbitrary code, a
  shell command, or an unregistered action.
- **agent.py** -- ties the above together: `handle_chat_message()`
  (creates + plans + runs a task), `resume_task()`, `pause_task()`,
  `cancel_task()` (which also closes any browser session the task
  opened, rather than leaving it running).

### Configuration

```
AGENT_ENABLED=true
MAX_AGENT_STEPS=20
MAX_AGENT_RETRIES=2
AUTO_GENERATE_MATERIALS=true
AUTO_PREPARE_APPLICATIONS=true
AUTO_SUBMIT_APPLICATIONS=false
AUTO_SEND_MESSAGES=false
REQUIRE_APPROVAL_FOR_EXTERNAL_ACTIONS=true
```

There's no separate `AGENT_DRY_RUN` -- `application.submit` reuses
Step 5's existing `DRY_RUN` flag (and its `submission_guard` check)
rather than introducing a second identical setting; the agent's own
approval gate sits in *front* of that check, it doesn't replace it. Two
independent things both have to agree before a real click ever happens.

### What's intentionally not here

Streaming (`POST /agent/chat/stream`) and real connectors
(email/calendar/LinkedIn/job-board outreach) are both explicitly
optional in the spec this step was built from, and aren't implemented --
streaming would complicate the architecture for little benefit at this
scale, and connectors need a real integration target before an
interface is worth committing to. Nothing here ever mass-messages
recruiters, mass-applies without review, or bypasses an application
limit -- there is no tool that sends an external message at all yet.

Full Step 8 endpoint list: `POST /agent/chat`, `GET /agent/tasks`,
`GET /agent/tasks/{id}`, `POST /agent/tasks/{id}/pause`,
`POST /agent/tasks/{id}/resume`, `POST /agent/tasks/{id}/cancel`,
`GET /agent/tasks/{id}/plan`, `GET /agent/tasks/{id}/events`,
`GET /agent/tasks/{id}/approvals`,
`POST /agent/approvals/{id}/approve`,
`POST /agent/approvals/{id}/reject`, `GET /agent/usage`.

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

`tests/test_discovery.py` covers Step 2b: each source adapter's parsing
against realistic mocked HTTP responses (never real network calls) --
including Greenhouse/Lever's 404-means-not-on-this-ATS handling, Adzuna/
USAJobs raising a clear configuration error when their keys aren't set,
and RemoteOK's feed's own legal-notice first element being skipped
correctly -- the dedup-aware ingest path (by external id, then by
canonical URL/description hash, matching an already-known job even
across sources), orchestration's per-source error isolation (one source
failing never blocks the others), goal-over-profile query precedence,
and the API endpoints.

`tests/test_agent.py` covers Step 8's 73 tests: the tool registry (no
duplicate names, every tool has a schema), the approval policy (LOW
never gates, MEDIUM only for the always-listed tools, HIGH always gates
even if a caller forgot to declare it), the full task/plan/event/
approval DB layer, deterministic intent detection against every example
command from the spec, plan validation, the executor's control flow
(clean completion, the approval gate stopping and then correctly
resuming on both approve and reject, `MAX_AGENT_STEPS` pausing rather
than failing, retries recovering a transient failure while
`application.submit` is never retried even once), `cv.generate`'s
idempotency (reuses an already-approved version instead of generating a
duplicate), conversational follow-up resolution, prompt-injection
wrapping, a dedicated security section (unregistered tools rejected,
malicious arguments schema-rejected, expired approvals can't be
approved, duplicate submissions prevented, cancelling a task closes its
open browser session), every API endpoint, and a synthetic end-to-end
prepare-then-approve-then-submit workflow that never leaves `DRY_RUN`.
Two tests drive the *entire* `application.submit` browser sequence
against real local Playwright fixtures (`test_application.html`,
`test_application_captcha.html`) rather than mocking it away: one proves
a genuine salary field correctly pauses the task and resuming after
answering it via the normal Step 5 endpoint reaches the approval gate;
the other proves a detected CAPTCHA pauses cleanly and re-checks itself
on resume rather than being solved, skipped, or silently passed through
-- both run through the `client` TestClient throughout (never a bare
`await agent_module...` call), since a Playwright session opened on one
event loop and closed from another hangs forever, a real hazard this
suite hit once while writing these tests and fixed by following the
same pattern `test_browser_application_e2e.py` already established.

`tests/test_resume_import.py` covers Step 1b: text extraction (PDF via
`pypdf`, plain text, rejecting unsupported formats and unreadable files
*before* ever calling the AI), parsing with the OpenAI call mocked
(matching `test_cv_customization.py`'s pattern), confirming into a new
profile vs. an existing one, refusing to confirm when there's neither a
profile nor enough contact info to create one, confirming twice
(rejected), every extracted row landing `verified: false` with no
exceptions, rejecting an import writes nothing at all, every API
endpoint, and the two agent tools (`career.confirm_resume_import`
always requires approval, and actually running it through the agent
still produces unverified rows).

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
- **Discovery** (`/discovery`) -- the Step 2b job discovery run trigger,
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
│   │   ├── api/                   One router per resource (incl. jobs.py, cvs.py, applications.py, agent.py, resume_import.py)
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
│   │   │   ├── discovery_service.py       Step 2b: builds the search query, runs each source, logs a DiscoveryRun
│   │   │   └── resume_import_service.py   Step 1b: extract -> AI parse -> pending review -> confirm (unverified) or reject
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
│   │   ├── discovery/                     Step 2b: one adapter per public job source, no LLM involved
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
│   │   │   ├── recommendation_outputs.py    Step 7 LLM output schema
│   │   │   ├── resume_parse_prompts.py      Step 1b prompt (extract, never invent)
│   │   │   └── resume_parse_outputs.py      Step 1b LLM output schema
│   │   ├── scripts/
│   │   │   └── analyze_job.py     Manual end-to-end demo script (Step 2)
│   │   ├── agent/                         Step 8: orchestrator over Steps 1-7, no reimplementation
│   │   │   ├── tool_registry.py           ~46 ToolSpecs (schema/permission/risk/handler)
│   │   │   ├── tools/                     One module per domain; handlers call existing services/routers
│   │   │   ├── tool_router.py             Validates args, invokes, normalizes {success,data,warnings,errors}
│   │   │   ├── planner.py                 Deterministic intent regexes + LLM classification fallback + plan templates
│   │   │   ├── executor.py                The controlled step-by-step loop, approval gating, retries, MAX_AGENT_STEPS
│   │   │   ├── permissions.py             The LOW/MEDIUM/HIGH approval policy
│   │   │   ├── approval_manager.py        request/approve/reject/expire -- the only writer of AgentApproval.status
│   │   │   ├── task_manager.py            DB access layer for AgentTask/AgentPlanStep/AgentEvent/AgentApproval
│   │   │   ├── memory.py                  Resolves conversational follow-ups against a prior task's own result
│   │   │   ├── validators.py              Pre-flight plan validation + untrusted-text wrapping (prompt-injection defense)
│   │   │   ├── state.py                   AgentState snapshot assembled from the DB rows
│   │   │   ├── prompts.py                 Intent-classification schema/prompt (the LLM's only role here)
│   │   │   ├── errors.py                  Agent-layer exception hierarchy
│   │   │   ├── agent.py                   handle_chat_message/resume_task/pause_task/cancel_task
│   │   │   └── __main__.py                `python -m app.agent <command>` CLI
│   │   └── db/                    Engine/session, declarative Base
│   ├── alembic/                   Migrations (Steps 1-8, applied in order)
│   ├── tests/                     pytest suite + tests/fixtures/ (local HTML, Step 5 only); test_agent.py for Step 8
│   ├── requirements.txt
│   ├── pytest.ini
│   ├── launchd/
│   │   └── com.jobiest.career-agent-backend.plist.example  Step 2b: persistent macOS service template
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
scraped by Step 2b (see `app/discovery/base.py`) -- jobs from either stay
a manual paste/URL flow through Step 2. Greenhouse/Lever discovery only
searches companies you've explicitly listed in your job-search goal's
`target_companies` -- there's no cross-company search API for either, by
design on their end, not a gap in this implementation. Step 8's agent
doesn't stream progress (`POST /agent/chat/stream` was explicitly
optional in its own spec) and has no real email/calendar/LinkedIn/
job-board connectors yet -- `interview.py`-style tool modules are the
natural place to add one once a real integration target exists, gated
behind the same approval policy every `EXTERNAL_ACTION` tool already
goes through.
