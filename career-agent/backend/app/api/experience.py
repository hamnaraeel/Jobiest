from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.models.enums import EntityType
from app.models.experience import Experience, ExperienceBullet
from app.models.profile import CareerProfile
from app.schemas.experience import ExperienceCreate, ExperienceRead
from app.services.validation_service import to_read_schema

router = APIRouter(prefix="/experience", tags=["experience"])

_NESTED = [("bullets", EntityType.EXPERIENCE_BULLET)]


@router.get("", response_model=list[ExperienceRead])
def list_experience(profile_id: int | None = None, db: Session = Depends(get_db)):
    stmt = select(Experience)
    if profile_id is not None:
        stmt = stmt.where(Experience.profile_id == profile_id)
    rows = db.execute(stmt).scalars().all()
    return [to_read_schema(db, r, ExperienceRead, EntityType.EXPERIENCE, nested=_NESTED) for r in rows]


@router.post("", response_model=ExperienceRead, status_code=status.HTTP_201_CREATED)
def create_experience(payload: ExperienceCreate, db: Session = Depends(get_db)):
    if db.get(CareerProfile, payload.profile_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No profile with id={payload.profile_id}")

    data = payload.model_dump(exclude={"bullets"})
    row = Experience(**data)
    db.add(row)
    db.flush()

    for bullet in payload.bullets:
        db.add(ExperienceBullet(experience_id=row.id, **bullet.model_dump()))

    db.commit()
    db.refresh(row)
    return to_read_schema(db, row, ExperienceRead, EntityType.EXPERIENCE, nested=_NESTED)
