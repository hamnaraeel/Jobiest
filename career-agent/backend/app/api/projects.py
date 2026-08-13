from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.models.enums import EntityType
from app.models.profile import CareerProfile
from app.models.project import Project, ProjectResult
from app.schemas.project import ProjectCreate, ProjectRead
from app.services.validation_service import orm_kwargs, to_read_schema

router = APIRouter(prefix="/projects", tags=["projects"])

_NESTED = [("results", EntityType.PROJECT_RESULT)]


@router.get("", response_model=list[ProjectRead])
def list_projects(profile_id: int | None = None, db: Session = Depends(get_db)):
    stmt = select(Project)
    if profile_id is not None:
        stmt = stmt.where(Project.profile_id == profile_id)
    rows = db.execute(stmt).scalars().all()
    return [to_read_schema(db, r, ProjectRead, EntityType.PROJECT, nested=_NESTED) for r in rows]


@router.post("", response_model=ProjectRead, status_code=status.HTTP_201_CREATED)
def create_project(payload: ProjectCreate, db: Session = Depends(get_db)):
    if db.get(CareerProfile, payload.profile_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No profile with id={payload.profile_id}")

    data = orm_kwargs(payload, exclude={"results"}, url_fields=("github_url", "demo_url"))
    row = Project(**data)
    db.add(row)
    db.flush()

    for result in payload.results:
        db.add(ProjectResult(project_id=row.id, **result.model_dump()))

    db.commit()
    db.refresh(row)
    return to_read_schema(db, row, ProjectRead, EntityType.PROJECT, nested=_NESTED)
