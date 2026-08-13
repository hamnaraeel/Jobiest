from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.models.certification import Certification
from app.models.enums import EntityType
from app.models.profile import CareerProfile
from app.schemas.certification import CertificationCreate, CertificationRead
from app.services.validation_service import orm_kwargs, to_read_schema

router = APIRouter(prefix="/certifications", tags=["certifications"])


@router.get("", response_model=list[CertificationRead])
def list_certifications(profile_id: int | None = None, db: Session = Depends(get_db)):
    stmt = select(Certification)
    if profile_id is not None:
        stmt = stmt.where(Certification.profile_id == profile_id)
    rows = db.execute(stmt).scalars().all()
    return [to_read_schema(db, r, CertificationRead, EntityType.CERTIFICATION) for r in rows]


@router.post("", response_model=CertificationRead, status_code=status.HTTP_201_CREATED)
def create_certification(payload: CertificationCreate, db: Session = Depends(get_db)):
    if db.get(CareerProfile, payload.profile_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No profile with id={payload.profile_id}")

    row = Certification(**orm_kwargs(payload, url_fields=("credential_url",)))
    db.add(row)
    db.commit()
    db.refresh(row)
    return to_read_schema(db, row, CertificationRead, EntityType.CERTIFICATION)
