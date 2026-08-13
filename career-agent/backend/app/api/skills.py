from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.models.enums import EntityType
from app.models.profile import CareerProfile
from app.models.skill import Skill
from app.schemas.skill import SkillCreate, SkillRead
from app.services.validation_service import to_read_schema

router = APIRouter(prefix="/skills", tags=["skills"])


@router.get("", response_model=list[SkillRead])
def list_skills(profile_id: int | None = None, db: Session = Depends(get_db)):
    stmt = select(Skill)
    if profile_id is not None:
        stmt = stmt.where(Skill.profile_id == profile_id)
    skills = db.execute(stmt).scalars().all()
    return [to_read_schema(db, s, SkillRead, EntityType.SKILL) for s in skills]


@router.post("", response_model=SkillRead, status_code=status.HTTP_201_CREATED)
def create_skill(payload: SkillCreate, db: Session = Depends(get_db)):
    if db.get(CareerProfile, payload.profile_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No profile with id={payload.profile_id}")

    skill = Skill(**payload.model_dump())
    db.add(skill)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, f"Skill '{payload.name}' already exists for this profile.")
    db.refresh(skill)
    return to_read_schema(db, skill, SkillRead, EntityType.SKILL)
