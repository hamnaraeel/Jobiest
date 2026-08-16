import logging

from fastapi import FastAPI

import app.models  # noqa: F401  (registers all models on Base.metadata)

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
    applications,
    certifications,
    cvs,
    education,
    evidence,
    experience,
    jobs,
    profile,
    projects,
    research,
    skills,
)

app = FastAPI(
    title="Career Agent",
    description=(
        "Single source of truth for verified career facts, job ingestion/analysis/"
        "matching, truthful source-traceable CV customization, and locally-generated "
        "(Ollama, no paid API) cover letters and application answers. Nothing here is "
        "ever invented: every fact carries a `verified` flag, every match status "
        "traces back to specific profile evidence or is honestly marked missing/"
        "unknown, and every generated claim traces back to a real profile row or is "
        "rejected/flagged for manual input rather than guessed."
    ),
    version="0.4.0",
)

app.include_router(profile.router)
app.include_router(skills.router)
app.include_router(education.router)
app.include_router(experience.router)
app.include_router(projects.router)
app.include_router(certifications.router)
app.include_router(achievements.router)
app.include_router(research.router)
app.include_router(evidence.router)
app.include_router(jobs.router)
app.include_router(cvs.jobs_cv_router)
app.include_router(cvs.cvs_router)
app.include_router(applications.jobs_router)
app.include_router(applications.cover_letters_router)
app.include_router(applications.answers_router)


@app.get("/health", tags=["health"])
def health():
    return {"status": "ok"}
