from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.schemas.profile import CareerProfileCreate, CareerProfileExport, CareerProfileRead, CareerProfileUpdate
from app.services import profile_service

router = APIRouter(prefix="/profile", tags=["profile"])


@router.get("", response_model=CareerProfileRead)
def get_profile(db: Session = Depends(get_db)):
    profile = profile_service.get_default_profile(db)
    if profile is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No career profile exists yet. POST /profile to create one.")
    return profile


@router.post("", response_model=CareerProfileRead, status_code=status.HTTP_201_CREATED)
def create_profile(payload: CareerProfileCreate, db: Session = Depends(get_db)):
    return profile_service.create_profile(db, payload)


@router.put("", response_model=CareerProfileRead)
def update_profile(payload: CareerProfileUpdate, db: Session = Depends(get_db)):
    profile = profile_service.get_default_profile(db)
    if profile is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No career profile exists yet. POST /profile to create one.")
    return profile_service.update_profile(db, profile, payload)


@router.get("/export", response_model=CareerProfileExport)
def export_profile(db: Session = Depends(get_db)):
    profile = profile_service.get_default_profile(db)
    if profile is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No career profile exists yet. POST /profile to create one.")
    return profile_service.export_profile(db, profile)


@router.post("/import", response_model=CareerProfileRead, status_code=status.HTTP_201_CREATED)
def import_profile(payload: dict, db: Session = Depends(get_db)):
    try:
        return profile_service.import_profile(db, payload)
    except (KeyError, TypeError) as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Malformed career profile export: {exc}")
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "A profile with this email already exists. Import always creates a new profile, "
            "so re-importing the same export requires changing the email first.",
        )
