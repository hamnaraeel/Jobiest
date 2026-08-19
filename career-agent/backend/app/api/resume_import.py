import logging

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai.client import AIConfigurationError
from app.db.database import get_db
from app.models.resume_import import ResumeImport
from app.schemas.profile import CareerProfileRead
from app.schemas.resume_import import ResumeImportConfirmRequest, ResumeImportListResponse, ResumeImportRead
from app.services.resume_import_service import (
    AIResponseError,
    ResumeImportError,
    confirm_import,
    parse_resume,
    reject_import,
)

logger = logging.getLogger("app.api.resume_import")

router = APIRouter(prefix="/profile/resume", tags=["profile"])


def _get_import_or_404(db: Session, import_id: int) -> ResumeImport:
    row = db.get(ResumeImport, import_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No resume import with id={import_id}")
    return row


@router.post("/upload", response_model=ResumeImportRead, status_code=status.HTTP_201_CREATED)
async def upload_resume(file: UploadFile = File(...), db: Session = Depends(get_db)):
    """Extracts text (PDF or plain text) and runs AI structured
    extraction into Career Profile shape -- this only ever creates a
    ResumeImport row for review; nothing is written to the Career
    Profile until POST .../imports/{id}/confirm. Requires OPENAI_API_KEY,
    same as Step 2's job analysis."""

    content = await file.read()
    try:
        return parse_resume(db, file.filename or "resume", content)
    except ResumeImportError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))
    except AIConfigurationError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc))
    except AIResponseError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc))


@router.get("/imports", response_model=ResumeImportListResponse)
def list_resume_imports(db: Session = Depends(get_db)):
    total = db.execute(select(func.count(ResumeImport.id))).scalar_one()
    items = db.execute(select(ResumeImport).order_by(ResumeImport.created_at.desc())).scalars().all()
    return ResumeImportListResponse(items=items, total=total)


@router.get("/imports/{import_id}", response_model=ResumeImportRead)
def get_resume_import(import_id: int, db: Session = Depends(get_db)):
    return _get_import_or_404(db, import_id)


@router.post("/imports/{import_id}/confirm", response_model=CareerProfileRead)
def confirm_resume_import(import_id: int, payload: ResumeImportConfirmRequest = ResumeImportConfirmRequest(), db: Session = Depends(get_db)):
    """The only endpoint that actually writes parsed resume data into the
    Career Profile -- every row it creates is verified=False, regardless
    of what the AI extracted. Never called automatically."""

    resume_import = _get_import_or_404(db, import_id)
    try:
        return confirm_import(db, resume_import, profile_id=payload.profile_id)
    except ResumeImportError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))


@router.post("/imports/{import_id}/reject", response_model=ResumeImportRead)
def reject_resume_import(import_id: int, db: Session = Depends(get_db)):
    resume_import = _get_import_or_404(db, import_id)
    try:
        return reject_import(db, resume_import)
    except ResumeImportError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))
