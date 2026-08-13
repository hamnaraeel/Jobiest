from fastapi import FastAPI

import app.models  # noqa: F401  (registers all models on Base.metadata)
from app.api import (
    achievements,
    certifications,
    education,
    evidence,
    experience,
    profile,
    projects,
    research,
    skills,
)

app = FastAPI(
    title="Career Agent - Career Knowledge Base",
    description=(
        "Single source of truth for verified career facts. Nothing here is "
        "ever invented: every fact carries a `verified` flag, and verified "
        "facts are expected to be backed by an Evidence record."
    ),
    version="0.1.0",
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


@app.get("/health", tags=["health"])
def health():
    return {"status": "ok"}
