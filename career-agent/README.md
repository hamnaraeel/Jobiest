# Career Agent — Step 1: Career Profile & Knowledge Base

The foundation of an AI-powered job application agent: a structured,
verified store of your career facts (education, experience, projects,
skills, research, certifications, achievements) with an evidence system
that prevents any future AI layer from inventing experience you don't
have.

This step deliberately does **not** include job scraping, browser
automation, application submission, CV/cover-letter generation, or
autonomous agents — those come later. See
[`docs/career-profile-schema.md`](docs/career-profile-schema.md) for the
full data model and the truth/verification rules.

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

`OPENAI_API_KEY` is not used by anything in this step — it's reserved for
the CV/cover-letter generation step that comes later.

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

Full endpoint list: `GET/POST/PUT /profile`, `GET /profile/export`,
`POST /profile/import`, and `GET/POST` for `/skills`, `/education`,
`/experience`, `/projects`, `/certifications`, `/achievements`,
`/research`, `/evidence`.

## 8. Testing

Tests run against a real PostgreSQL database (with pgvector) — point
`DATABASE_URL` at a disposable database before running them; the suite
drops and recreates the schema itself:

```bash
export DATABASE_URL=postgresql+psycopg2://postgres:postgres@localhost:5432/career_agent_test
pytest -v
```

## Project structure

```
career-agent/
├── backend/
│   ├── app/
│   │   ├── main.py               FastAPI app, router registration
│   │   ├── config.py              Settings (DATABASE_URL, OPENAI_API_KEY)
│   │   ├── api/                   One router per resource
│   │   ├── models/                SQLAlchemy models + shared enums
│   │   ├── schemas/                Pydantic Create/Update/Read schemas
│   │   ├── services/
│   │   │   ├── profile_service.py     CRUD, export/import
│   │   │   └── validation_service.py  Evidence lookups, truth rules
│   │   └── db/                    Engine/session, declarative Base
│   ├── alembic/                   Migrations
│   ├── tests/                     pytest suite
│   ├── requirements.txt
│   └── .env.example
├── data/
│   ├── career_profile.json        Placeholder seed data
│   └── README.md                  How to fill it in
├── docs/
│   └── career-profile-schema.md   Full schema + verification rules
└── README.md
```

## What's next (not built yet)

Job scraping, job/CV matching and scoring, CV tailoring, cover letter
generation, user approval workflow, browser automation for application
submission, and application/outcome tracking. The schema here is
deliberately structured (foreign keys, evidence links, reserved embedding
columns) so those steps can be added without reshaping what already
exists.
