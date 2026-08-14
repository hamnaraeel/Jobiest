"""Manual end-to-end demo of the Step 2 pipeline.

Usage:
    python -m app.scripts.analyze_job data/test_job_description.txt

Ingests the given job description file, runs AI analysis (requires
OPENAI_API_KEY), matches it against the current career profile, and
prints a human-readable summary. Requires a career profile to already
exist (see Step 1).
"""

import sys

from app.ai.client import AIConfigurationError
from app.db.database import SessionLocal
from app.services.job_analysis_service import AIResponseError, AnalysisInputError, analyze_job
from app.services.job_ingestion_service import ingest_job
from app.services.job_matching_service import MatchInputError, compute_match
from app.services.profile_service import get_default_profile

SEPARATOR = "=" * 40


def _print_section(title: str):
    print(SEPARATOR)
    print(title)
    print("=" * len(title))
    print()


def _print_bullets(label: str, items: list[str]):
    print(f"{label}:")
    print()
    if not items:
        print("(none)")
    for item in items:
        print(f"* {item}")
    print()


def main(path: str) -> int:
    with open(path, encoding="utf-8") as f:
        description = f.read()

    db = SessionLocal()
    try:
        if get_default_profile(db) is None:
            print("No career profile found. Complete Step 1 (POST /profile or import "
                  "data/career_profile.json) before running this script.")
            return 1

        result = ingest_job(db, url=None, description=description)
        job = result.job

        try:
            job = analyze_job(db, job)
        except AIConfigurationError as exc:
            print(f"Cannot run AI analysis: {exc}")
            return 1
        except (AnalysisInputError, AIResponseError) as exc:
            print(f"Job analysis failed: {exc}")
            return 1

        required_skills = [r.skill_name or r.requirement_text for r in job.requirements
                            if r.category.value == "technical_skill" and r.required]
        preferred_skills = [r.skill_name or r.requirement_text for r in job.requirements
                             if r.category.value == "technical_skill" and not r.required]
        experience = [r.requirement_text for r in job.requirements if r.category.value == "experience"]

        _print_section("JOB ANALYSIS")
        print("Title:")
        print(job.title or "(not found)")
        print()
        print("Company:")
        print(job.company or "(not found)")
        print()
        _print_bullets("Required Skills", required_skills)
        _print_bullets("Preferred Skills", preferred_skills)
        _print_bullets("Experience", experience)

        try:
            match = compute_match(db, job)
        except MatchInputError as exc:
            print(f"Matching failed: {exc}")
            return 1

        _print_section("MATCH RESULT")
        print(f"Score: {match.overall_score}%")
        print()
        print(f"Recommendation: {match.recommendation.value.upper()}")
        print()
        print("Strengths:")
        for s in match.strengths:
            print(f"✓ {s}")
        print()
        print("Partial:")
        for p in [d["requirement"] for d in match.partial_requirements]:
            print(f"~ {p}")
        print()
        print("Missing:")
        for m in [d["requirement"] for d in match.missing_requirements]:
            print(f"✗ {m}")
        if match.critical_gaps:
            print()
            print("Critical gaps:")
            for g in match.critical_gaps:
                print(f"!! {g}")
        print()
        print(SEPARATOR)
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python -m app.scripts.analyze_job <path-to-job-description.txt>")
        sys.exit(2)
    sys.exit(main(sys.argv[1]))
