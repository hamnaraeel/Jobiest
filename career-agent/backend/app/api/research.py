from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.models.enums import EntityType
from app.models.profile import CareerProfile
from app.models.research import Research
from app.schemas.research import ResearchCreate, ResearchRead
from app.services.validation_service import to_read_schema

router = APIRouter(prefix="/research", tags=["research"])


@router.get("", response_model=list[ResearchRead])
def list_research(profile_id: int | None = None, db: Session = Depends(get_db)):
    stmt = select(Research)
    if profile_id is not None:
        stmt = stmt.where(Research.profile_id == profile_id)
    rows = db.execute(stmt).scalars().all()
    return [to_read_schema(db, r, ResearchRead, EntityType.RESEARCH) for r in rows]


@router.post("", response_model=ResearchRead, status_code=status.HTTP_201_CREATED)
def create_research(payload: ResearchCreate, db: Session = Depends(get_db)):
    if db.get(CareerProfile, payload.profile_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No profile with id={payload.profile_id}")

    row = Research(**payload.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return to_read_schema(db, row, ResearchRead, EntityType.RESEARCH)
