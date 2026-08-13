from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.models.education import Education
from app.models.enums import EntityType
from app.models.profile import CareerProfile
from app.schemas.education import EducationCreate, EducationRead
from app.services.validation_service import to_read_schema

router = APIRouter(prefix="/education", tags=["education"])


@router.get("", response_model=list[EducationRead])
def list_education(profile_id: int | None = None, db: Session = Depends(get_db)):
    stmt = select(Education)
    if profile_id is not None:
        stmt = stmt.where(Education.profile_id == profile_id)
    rows = db.execute(stmt).scalars().all()
    return [to_read_schema(db, r, EducationRead, EntityType.EDUCATION) for r in rows]


@router.post("", response_model=EducationRead, status_code=status.HTTP_201_CREATED)
def create_education(payload: EducationCreate, db: Session = Depends(get_db)):
    if db.get(CareerProfile, payload.profile_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No profile with id={payload.profile_id}")

    row = Education(**payload.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return to_read_schema(db, row, EducationRead, EntityType.EDUCATION)
