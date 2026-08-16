"""Resolves and uploads the approved CV/cover letter PDF to file-input
fields. Never uploads a draft/rejected/unvalidated CV or cover letter
(spec sections 13-14) -- verified here, not just assumed by the caller.

Compiles a PDF lazily if an approved version doesn't have one on disk yet
(mirrors Step 4's cover-letter lazy-compile pattern; extends the same
idea to the CV, which is normally already compiled at generation time
but may not be if it was only ever previewed).
"""

from pathlib import Path

from playwright.async_api import Locator
from sqlalchemy.orm import Session

from app.models.cover_letter import CoverLetter
from app.models.cv_version import CVVersion
from app.models.enums import ApplicationMaterialStatus
from app.services import cv_render_service
from app.services.cover_letter_service import CoverLetterInputError, ensure_cover_letter_pdf


class UnapprovedMaterialError(ValueError):
    pass


def _ensure_cv_pdf(db: Session, cv_version: CVVersion) -> str:
    if cv_version.pdf_path and Path(cv_version.pdf_path).exists():
        return cv_version.pdf_path
    if not cv_version.latex_source:
        raise UnapprovedMaterialError("CV has no rendered content to compile a PDF from.")
    result = cv_render_service.compile_pdf(cv_version.latex_source, cv_version.job_id, cv_version.version_number)
    if not result.success:
        raise UnapprovedMaterialError(f"CV PDF compilation failed: {result.error}")
    cv_version.pdf_path = result.pdf_path
    db.commit()
    db.refresh(cv_version)
    return cv_version.pdf_path


def resolve_cv_pdf_path(db: Session, cv_version: CVVersion | None) -> str:
    if cv_version is None:
        raise UnapprovedMaterialError("No CV is associated with this application.")
    if cv_version.status != ApplicationMaterialStatus.APPROVED:
        raise UnapprovedMaterialError(f"CV status is '{cv_version.status.value}', not approved -- refusing to upload.")
    return _ensure_cv_pdf(db, cv_version)


def resolve_cover_letter_pdf_path(db: Session, cover_letter: CoverLetter | None) -> str:
    if cover_letter is None:
        raise UnapprovedMaterialError("No cover letter is associated with this application.")
    if cover_letter.status != ApplicationMaterialStatus.APPROVED:
        raise UnapprovedMaterialError(f"Cover letter status is '{cover_letter.status.value}', not approved -- refusing to upload.")
    try:
        return ensure_cover_letter_pdf(db, cover_letter)
    except CoverLetterInputError as exc:
        raise UnapprovedMaterialError(str(exc)) from exc


async def upload_file(locator: Locator, path: str) -> None:
    await locator.set_input_files(path)
