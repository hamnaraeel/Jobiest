from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.models.evidence import Evidence, EvidenceLink
from app.models.profile import CareerProfile
from app.schemas.evidence import EvidenceCreate, EvidenceRead
from app.services.validation_service import orm_kwargs

router = APIRouter(prefix="/evidence", tags=["evidence"])


@router.get("", response_model=list[EvidenceRead])
def list_evidence(profile_id: int | None = None, db: Session = Depends(get_db)):
    stmt = select(Evidence)
    if profile_id is not None:
        stmt = stmt.where(Evidence.profile_id == profile_id)
    return db.execute(stmt).scalars().all()


@router.post("", response_model=EvidenceRead, status_code=status.HTTP_201_CREATED)
def create_evidence(payload: EvidenceCreate, db: Session = Depends(get_db)):
    if db.get(CareerProfile, payload.profile_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No profile with id={payload.profile_id}")

    row = Evidence(**orm_kwargs(payload, exclude={"links"}, url_fields=("source_url",)))
    db.add(row)
    db.flush()

    for link in payload.links:
        db.add(EvidenceLink(evidence_id=row.id, **link.model_dump()))

    db.commit()
    db.refresh(row)
    return row
