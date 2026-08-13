from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.models.achievement import Achievement
from app.models.enums import EntityType
from app.models.profile import CareerProfile
from app.schemas.achievement import AchievementCreate, AchievementRead
from app.services.validation_service import to_read_schema

router = APIRouter(prefix="/achievements", tags=["achievements"])


@router.get("", response_model=list[AchievementRead])
def list_achievements(profile_id: int | None = None, db: Session = Depends(get_db)):
    stmt = select(Achievement)
    if profile_id is not None:
        stmt = stmt.where(Achievement.profile_id == profile_id)
    rows = db.execute(stmt).scalars().all()
    return [to_read_schema(db, r, AchievementRead, EntityType.ACHIEVEMENT) for r in rows]


@router.post("", response_model=AchievementRead, status_code=status.HTTP_201_CREATED)
def create_achievement(payload: AchievementCreate, db: Session = Depends(get_db)):
    if db.get(CareerProfile, payload.profile_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No profile with id={payload.profile_id}")

    row = Achievement(**payload.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return to_read_schema(db, row, AchievementRead, EntityType.ACHIEVEMENT)
