import logging
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai.client import AIConfigurationError
from app.db.database import get_db
from app.models.cv_change import CVChange
from app.models.cv_version import CVVersion
from app.models.enums import CVSectionType, CVStatus
from app.models.job import Job
from app.schemas.cv import (
    CVComparisonResponse,
    CVListResponse,
    CVPreviewResponse,
    CVStatusUpdateRequest,
    CVVersionRead,
)
from app.schemas.cv_generation import CVGenerateRequest
from app.services import cv_comparison_service
from app.services.cv_customization_service import AIResponseError, CVGenerationInputError, generate_cv

logger = logging.getLogger("app.api.cvs")

jobs_cv_router = APIRouter(prefix="/jobs", tags=["cv"])
cvs_router = APIRouter(prefix="/cvs", tags=["cv"])


def _get_job_or_404(db: Session, job_id: int) -> Job:
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No job with id={job_id}")
    return job


def _get_cv_or_404(db: Session, cv_id: int) -> CVVersion:
    cv = db.get(CVVersion, cv_id)
    if cv is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No CV version with id={cv_id}")
    return cv


def _run_generation(db: Session, job_id: int, payload: CVGenerateRequest, compile_pdf_flag: bool) -> CVVersion:
    job = _get_job_or_404(db, job_id)
    try:
        return generate_cv(db, job, template_name=payload.template_name, compile_pdf_flag=compile_pdf_flag)
    except CVGenerationInputError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))
    except AIConfigurationError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc))
    except AIResponseError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc))


@jobs_cv_router.post("/{job_id}/cv/generate", response_model=CVVersionRead, status_code=status.HTTP_201_CREATED)
def generate_job_cv(job_id: int, payload: CVGenerateRequest = CVGenerateRequest(), db: Session = Depends(get_db)):
    """Full pipeline: plan -> content -> validate -> LaTeX -> PDF -> store.
    Always creates a new CVVersion (V1, V2, V3, ...) -- never overwrites
    a previous one. Requires OPENAI_API_KEY and the job to be analyzed."""

    return _run_generation(db, job_id, payload, compile_pdf_flag=payload.compile_pdf)


@jobs_cv_router.post("/{job_id}/cv/preview", response_model=CVPreviewResponse)
def preview_job_cv(job_id: int, payload: CVGenerateRequest = CVGenerateRequest(), db: Session = Depends(get_db)):
    """Same pipeline as /generate, minus the PDF compilation step -- lets
    the content be reviewed before spending a pdflatex run on it. Still
    creates a CVVersion row (draft/validated, no pdf_path) so the preview
    is inspectable via GET /cvs/{id} afterward."""

    cv = _run_generation(db, job_id, payload, compile_pdf_flag=False)
    return CVPreviewResponse(
        version_id=cv.id,
        summary=cv.summary or "",
        skills=cv.skills,
        experience=cv.experience,
        projects=cv.projects,
        education=cv.education,
        warnings=cv.warnings,
    )


@cvs_router.get("", response_model=CVListResponse)
def list_cvs(
    db: Session = Depends(get_db),
    job_id: int | None = None,
    status_filter: CVStatus | None = Query(None, alias="status"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    stmt = select(CVVersion)
    count_stmt = select(func.count(CVVersion.id))
    if job_id is not None:
        stmt = stmt.where(CVVersion.job_id == job_id)
        count_stmt = count_stmt.where(CVVersion.job_id == job_id)
    if status_filter is not None:
        stmt = stmt.where(CVVersion.status == status_filter)
        count_stmt = count_stmt.where(CVVersion.status == status_filter)

    total = db.execute(count_stmt).scalar_one()
    items = db.execute(stmt.order_by(CVVersion.created_at.desc()).limit(limit).offset(offset)).scalars().all()
    return CVListResponse(items=[CVVersionRead.model_validate(c) for c in items], total=total, limit=limit, offset=offset)


@cvs_router.get("/{cv_id}", response_model=CVVersionRead)
def get_cv(cv_id: int, db: Session = Depends(get_db)):
    return _get_cv_or_404(db, cv_id)


@cvs_router.get("/{cv_id}/download")
def download_cv(cv_id: int, db: Session = Depends(get_db)):
    cv = _get_cv_or_404(db, cv_id)
    if not cv.pdf_path:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "This CV version has no compiled PDF yet.")
    pdf_path = Path(cv.pdf_path)
    if not pdf_path.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "The PDF file for this CV version is missing on disk.")
    return FileResponse(pdf_path, media_type="application/pdf", filename=f"{cv.version_name}.pdf")


@cvs_router.get("/{cv_id}/comparison", response_model=CVComparisonResponse)
def get_cv_comparison(cv_id: int, db: Session = Depends(get_db)):
    cv = _get_cv_or_404(db, cv_id)
    changes = db.execute(select(CVChange).where(CVChange.cv_version_id == cv_id)).scalars().all()
    return cv_comparison_service.build_comparison_response(cv, changes)


@cvs_router.patch("/{cv_id}/status", response_model=CVVersionRead)
def update_cv_status(cv_id: int, payload: CVStatusUpdateRequest, db: Session = Depends(get_db)):
    """Human-in-the-loop approval step. A CV is never auto-approved by
    generation -- it reaches at most 'validated'. A future application
    agent is expected to only ever use status == approved."""

    cv = _get_cv_or_404(db, cv_id)
    if cv.status == CVStatus.ARCHIVED:
        raise HTTPException(status.HTTP_409_CONFLICT, "This CV version is archived and cannot change status.")
    cv.status = payload.status
    db.commit()
    db.refresh(cv)
    return cv


@cvs_router.delete("/{cv_id}", response_model=CVVersionRead)
def delete_cv(cv_id: int, db: Session = Depends(get_db)):
    """Never hard-deletes a version (old versions are never destroyed
    automatically) -- this archives it instead, keeping the row, the PDF,
    and its full history intact but out of the active list."""

    cv = _get_cv_or_404(db, cv_id)
    cv.status = CVStatus.ARCHIVED
    db.commit()
    db.refresh(cv)
    return cv
