import logging
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse, PlainTextResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.client import AIConfigurationError, OllamaResponseError
from app.db.database import get_db
from app.models.application_answer import ApplicationAnswer
from app.models.application_question import ApplicationQuestion
from app.models.cover_letter import CoverLetter
from app.models.cv_version import CVVersion
from app.models.job import Job
from app.schemas.application_answer import (
    ApplicationAnswerRead,
    ApplicationAnswerStatusUpdateRequest,
    ApplicationQuestionCreate,
    ApplicationQuestionRead,
    ManualInputRequired,
)
from app.schemas.cover_letter import (
    CoverLetterGenerateRequest,
    CoverLetterListResponse,
    CoverLetterRead,
    CoverLetterStatusUpdateRequest,
)
from app.services import application_material_service
from app.services.application_answer_service import (
    AnswerInputError,
    ManualInputRequiredError,
    classify_question_type,
    generate_answer,
)
from app.services.cover_letter_service import (
    CoverLetterInputError,
    CoverLetterStyleError,
    ensure_cover_letter_pdf,
    generate_cover_letter,
)

logger = logging.getLogger("app.api.applications")

jobs_router = APIRouter(prefix="/jobs", tags=["applications"])
cover_letters_router = APIRouter(prefix="/cover-letters", tags=["applications"])
answers_router = APIRouter(prefix="/application-answers", tags=["applications"])


def _get_job_or_404(db: Session, job_id: int) -> Job:
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No job with id={job_id}")
    return job


def _get_cover_letter_or_404(db: Session, cover_letter_id: int) -> CoverLetter:
    cl = db.get(CoverLetter, cover_letter_id)
    if cl is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No cover letter with id={cover_letter_id}")
    return cl


def _get_question_or_404(db: Session, job_id: int, question_id: int) -> ApplicationQuestion:
    question = db.get(ApplicationQuestion, question_id)
    if question is None or question.job_id != job_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No application question with id={question_id} for job {job_id}")
    return question


def _latest_approved_or_latest_cv(db: Session, job_id: int) -> CVVersion | None:
    approved = db.execute(
        select(CVVersion).where(CVVersion.job_id == job_id, CVVersion.status == "approved")
        .order_by(CVVersion.version_number.desc()).limit(1)
    ).scalar_one_or_none()
    if approved:
        return approved
    return db.execute(
        select(CVVersion).where(CVVersion.job_id == job_id).order_by(CVVersion.version_number.desc()).limit(1)
    ).scalar_one_or_none()


# --- Cover letters -----------------------------------------------------


@jobs_router.post("/{job_id}/cover-letter/generate", response_model=CoverLetterRead, status_code=status.HTTP_201_CREATED)
def generate_job_cover_letter(job_id: int, payload: CoverLetterGenerateRequest = CoverLetterGenerateRequest(), db: Session = Depends(get_db)):
    """Requires an approved CV for this job (POST /jobs/{id}/cv/generate,
    then PATCH /cvs/{id}/status to approved) and a local Ollama model
    (OLLAMA_MODEL). Always creates a new version -- never overwrites."""

    job = _get_job_or_404(db, job_id)
    cv_version = _latest_approved_or_latest_cv(db, job_id)
    if cv_version is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "No CV version exists for this job yet -- generate one first.")

    try:
        return generate_cover_letter(
            db, job, cv_version, style=payload.style, length=payload.length,
            focus=payload.focus, instructions=payload.instructions,
        )
    except CoverLetterStyleError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))
    except CoverLetterInputError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))
    except AIConfigurationError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc))
    except OllamaResponseError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc))


@cover_letters_router.get("/{cover_letter_id}", response_model=CoverLetterRead)
def get_cover_letter(cover_letter_id: int, db: Session = Depends(get_db)):
    return _get_cover_letter_or_404(db, cover_letter_id)


@cover_letters_router.get("/{cover_letter_id}/versions", response_model=CoverLetterListResponse)
def get_cover_letter_versions(cover_letter_id: int, db: Session = Depends(get_db)):
    cl = _get_cover_letter_or_404(db, cover_letter_id)
    versions = db.execute(
        select(CoverLetter).where(CoverLetter.job_id == cl.job_id).order_by(CoverLetter.version_number)
    ).scalars().all()
    return CoverLetterListResponse(items=list(versions), total=len(versions))


@cover_letters_router.get("/{cover_letter_id}/download")
def download_cover_letter(cover_letter_id: int, format: str = Query("txt", pattern="^(txt|pdf)$"), db: Session = Depends(get_db)):
    cl = _get_cover_letter_or_404(db, cover_letter_id)
    if format == "txt":
        return PlainTextResponse(cl.content, headers={"Content-Disposition": f'attachment; filename="{cl.version_name}.txt"'})

    try:
        pdf_path = ensure_cover_letter_pdf(db, cl)
    except CoverLetterInputError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc))
    path = Path(pdf_path)
    if not path.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "PDF file missing on disk.")
    return FileResponse(path, media_type="application/pdf", filename=f"{cl.version_name}.pdf")


@cover_letters_router.post("/{cover_letter_id}/regenerate", response_model=CoverLetterRead, status_code=status.HTTP_201_CREATED)
def regenerate_cover_letter(cover_letter_id: int, payload: CoverLetterGenerateRequest = CoverLetterGenerateRequest(), db: Session = Depends(get_db)):
    cl = _get_cover_letter_or_404(db, cover_letter_id)
    job = _get_job_or_404(db, cl.job_id)
    cv_version = db.get(CVVersion, cl.cv_version_id)

    try:
        return generate_cover_letter(
            db, job, cv_version, style=payload.style, length=payload.length,
            focus=payload.focus, instructions=payload.instructions,
        )
    except CoverLetterStyleError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))
    except CoverLetterInputError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))
    except AIConfigurationError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc))
    except OllamaResponseError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc))


@cover_letters_router.patch("/{cover_letter_id}/status", response_model=CoverLetterRead)
def update_cover_letter_status(cover_letter_id: int, payload: CoverLetterStatusUpdateRequest, db: Session = Depends(get_db)):
    cl = _get_cover_letter_or_404(db, cover_letter_id)
    if cl.status.value == "archived":
        raise HTTPException(status.HTTP_409_CONFLICT, "This cover letter is archived and cannot change status.")
    cl.status = payload.status
    db.commit()
    db.refresh(cl)
    return cl


# --- Application questions & answers ----------------------------------


@jobs_router.post("/{job_id}/application-questions", response_model=ApplicationQuestionRead, status_code=status.HTTP_201_CREATED)
def create_application_question(job_id: int, payload: ApplicationQuestionCreate, db: Session = Depends(get_db)):
    job = _get_job_or_404(db, job_id)
    question = ApplicationQuestion(
        job_id=job.id,
        question=payload.question,
        question_type=payload.question_type or classify_question_type(payload.question),
        character_limit=payload.character_limit,
        word_limit=payload.word_limit,
        required=payload.required,
    )
    db.add(question)
    db.commit()
    db.refresh(question)
    return question


@jobs_router.get("/{job_id}/application-questions", response_model=list[ApplicationQuestionRead])
def list_application_questions(job_id: int, db: Session = Depends(get_db)):
    _get_job_or_404(db, job_id)
    return db.execute(select(ApplicationQuestion).where(ApplicationQuestion.job_id == job_id)).scalars().all()


@jobs_router.post("/{job_id}/application-questions/{question_id}/answer")
def generate_question_answer(job_id: int, question_id: int, db: Session = Depends(get_db)):
    job = _get_job_or_404(db, job_id)
    question = _get_question_or_404(db, job_id, question_id)

    try:
        answer = generate_answer(db, question, job)
    except ManualInputRequiredError as exc:
        return ManualInputRequired(question_type=exc.question_type, reason=exc.reason)
    except AnswerInputError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))
    except AIConfigurationError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc))
    except OllamaResponseError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc))

    return ApplicationAnswerRead.model_validate(answer)


@answers_router.get("/{answer_id}", response_model=ApplicationAnswerRead)
def get_application_answer(answer_id: int, db: Session = Depends(get_db)):
    answer = db.get(ApplicationAnswer, answer_id)
    if answer is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No application answer with id={answer_id}")
    return answer


@answers_router.patch("/{answer_id}/status", response_model=ApplicationAnswerRead)
def update_application_answer_status(answer_id: int, payload: ApplicationAnswerStatusUpdateRequest, db: Session = Depends(get_db)):
    answer = db.get(ApplicationAnswer, answer_id)
    if answer is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No application answer with id={answer_id}")
    if answer.status.value == "archived":
        raise HTTPException(status.HTTP_409_CONFLICT, "This answer is archived and cannot change status.")
    answer.status = payload.status
    db.commit()
    db.refresh(answer)
    return answer


# --- Application materials package --------------------------------------


@jobs_router.get("/{job_id}/application-materials")
def get_application_materials(job_id: int, db: Session = Depends(get_db)):
    job = _get_job_or_404(db, job_id)
    return application_material_service.build_application_material_package(db, job)
