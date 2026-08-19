import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import app.models  # noqa: F401  (registers all models on Base.metadata)
from app.config import get_settings
from app.scheduler import start_scheduler, stop_scheduler

# Structured logging for ingestion/parsing/AI calls/matching (see the
# `logger = logging.getLogger("app....")` calls throughout app/services and
# app/ai). Deliberately logs event descriptions and counts, never request
# bodies or settings values, so API keys/credentials can't end up in logs.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
)

from app.api import (
    achievements,
    agent,
    applications,
    browser_applications,
    certifications,
    cvs,
    discovery,
    education,
    evidence,
    experience,
    intelligence,
    jobs,
    profile,
    projects,
    research,
    resume_import,
    skills,
    tracking,
)


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Step 8: only actually starts a background thread if
    # DISCOVERY_SCHEDULER_ENABLED=true -- discovery itself always works
    # on-demand via POST /discovery/run regardless of this setting.
    start_scheduler()
    yield
    stop_scheduler()


app = FastAPI(
    lifespan=lifespan,
    title="Career Agent",
    description=(
        "Single source of truth for verified career facts, job ingestion/analysis/"
        "matching, truthful source-traceable CV customization, locally-generated "
        "(Ollama, no paid API) cover letters and application answers, a browser-"
        "assisted (never autonomous) application workflow, and job-search tracking "
        "with deterministic analytics, and an orchestrating agent (POST /agent/chat) "
        "that plans and executes the tools above for a high-level request without "
        "reimplementing any of them. Nothing here is ever invented: every fact "
        "carries a `verified` flag, every match status traces back to specific "
        "profile evidence or is honestly marked missing/unknown, every generated "
        "claim traces back to a real profile row or is rejected/flagged for manual "
        "input rather than guessed, and no submit button or external message is ever "
        "sent without explicit, separately-recorded user approval."
    ),
    version="0.10.0",
)

# Local-first only: allows the local React dev server (and any other
# configured local origin) to call this API directly. Never opened to
# arbitrary origins -- FRONTEND_ORIGINS defaults to just the Vite dev
# server ports and is fully configurable via .env.
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().frontend_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(profile.router)
app.include_router(resume_import.router)
app.include_router(skills.router)
app.include_router(education.router)
app.include_router(experience.router)
app.include_router(projects.router)
app.include_router(certifications.router)
app.include_router(achievements.router)
app.include_router(research.router)
app.include_router(evidence.router)

# Route matching is registration-order-sensitive: Starlette matches routes
# in the order they were added and does not prefer a literal path segment
# over a same-position `{param}` one. tracking.jobs_tracking_router's
# `GET /jobs/search` and tracking.applications_tracking_router's
# `GET /applications/search` / `GET /applications/export` must therefore
# be registered before jobs.router's `GET /jobs/{job_id}` and
# browser_applications.applications_router's `GET /applications/{application_id}`
# -- otherwise "search"/"export" would be swallowed as the id path param
# and 422 instead of reaching the intended endpoint.
app.include_router(tracking.dashboard_router)
app.include_router(tracking.jobs_tracking_router)
app.include_router(tracking.applications_tracking_router)
app.include_router(tracking.followups_router)
app.include_router(tracking.analytics_router)
app.include_router(tracking.notifications_router)
app.include_router(tracking.calendar_router)

app.include_router(jobs.router)
app.include_router(cvs.jobs_cv_router)
app.include_router(cvs.cvs_router)
app.include_router(applications.jobs_router)
app.include_router(applications.cover_letters_router)
app.include_router(applications.answers_router)
app.include_router(browser_applications.apply_router)
app.include_router(browser_applications.applications_router)

app.include_router(intelligence.intelligence_router)
app.include_router(intelligence.interview_prep_router)
app.include_router(intelligence.applications_rejection_router)

app.include_router(discovery.router)

app.include_router(agent.router)


@app.get("/health", tags=["health"])
def health():
    return {"status": "ok"}
