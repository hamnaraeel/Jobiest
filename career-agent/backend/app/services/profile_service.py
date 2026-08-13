from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.achievement import Achievement
from app.models.certification import Certification
from app.models.education import Education
from app.models.enums import EntityType
from app.models.evidence import Evidence, EvidenceLink
from app.models.experience import Experience, ExperienceBullet
from app.models.profile import CareerProfile
from app.models.project import Project, ProjectResult
from app.models.research import Research
from app.models.skill import Skill
from app.schemas.achievement import AchievementRead
from app.schemas.certification import CertificationRead
from app.schemas.education import EducationRead
from app.schemas.evidence import EvidenceRead
from app.schemas.experience import ExperienceRead
from app.schemas.profile import CareerProfileCreate, CareerProfileExport, CareerProfileRead, CareerProfileUpdate
from app.schemas.project import ProjectRead
from app.schemas.research import ResearchRead
from app.schemas.skill import SkillRead
from app.services.validation_service import to_read_schema


def get_profile(db: Session, profile_id: int) -> CareerProfile | None:
    return db.get(CareerProfile, profile_id)


def get_default_profile(db: Session) -> CareerProfile | None:
    """This is a single-user system: unless told otherwise, callers work
    against the first (and normally only) profile row."""
    return db.execute(select(CareerProfile).order_by(CareerProfile.id).limit(1)).scalar_one_or_none()


def create_profile(db: Session, payload: CareerProfileCreate) -> CareerProfile:
    profile = CareerProfile(**payload.model_dump(mode="json"))
    db.add(profile)
    db.commit()
    db.refresh(profile)
    return profile


def update_profile(db: Session, profile: CareerProfile, payload: CareerProfileUpdate) -> CareerProfile:
    updates = payload.model_dump(mode="json", exclude_unset=True)
    for field, value in updates.items():
        setattr(profile, field, value)
    db.commit()
    db.refresh(profile)
    return profile


def export_profile(db: Session, profile: CareerProfile) -> CareerProfileExport:
    return CareerProfileExport(
        profile=CareerProfileRead.model_validate(profile, from_attributes=True),
        educations=[to_read_schema(db, e, EducationRead, EntityType.EDUCATION).model_dump(mode="json") for e in profile.educations],
        experiences=[to_read_schema(db, e, ExperienceRead, EntityType.EXPERIENCE).model_dump(mode="json") for e in profile.experiences],
        projects=[to_read_schema(db, p, ProjectRead, EntityType.PROJECT).model_dump(mode="json") for p in profile.projects],
        skills=[to_read_schema(db, s, SkillRead, EntityType.SKILL).model_dump(mode="json") for s in profile.skills],
        certifications=[to_read_schema(db, c, CertificationRead, EntityType.CERTIFICATION).model_dump(mode="json") for c in profile.certifications],
        achievements=[to_read_schema(db, a, AchievementRead, EntityType.ACHIEVEMENT).model_dump(mode="json") for a in profile.achievements],
        research_items=[to_read_schema(db, r, ResearchRead, EntityType.RESEARCH).model_dump(mode="json") for r in profile.research_items],
        evidence=[EvidenceRead.model_validate(ev, from_attributes=True).model_dump(mode="json") for ev in profile.evidence_items],
    )


def import_profile(db: Session, payload: dict) -> CareerProfile:
    """Create a brand-new profile (and its child records) from an exported
    career_profile.json document. This never mutates an existing profile --
    it always inserts a new one, so importing can't silently overwrite
    verified data."""

    profile_data = payload["profile"]
    profile_data = {k: v for k, v in profile_data.items() if k not in {"id", "created_at", "updated_at"}}
    profile = CareerProfile(**profile_data)
    db.add(profile)
    db.flush()

    def strip(d: dict, extra: set[str] = frozenset()) -> dict:
        drop = {"id", "profile_id", "created_at", "updated_at", "evidence_ids"} | extra
        return {k: v for k, v in d.items() if k not in drop}

    # Old export id -> newly-inserted id, per entity type. Needed so that
    # EvidenceLink rows (which reference entity_id by old id) still point
    # at the right row after import, since every import creates fresh rows.
    id_map: dict[EntityType, dict[int, int]] = {et: {} for et in EntityType}

    for e in payload.get("educations", []):
        old_id = e.get("id")
        row = Education(profile_id=profile.id, **strip(e))
        db.add(row)
        db.flush()
        if old_id is not None:
            id_map[EntityType.EDUCATION][old_id] = row.id

    for e in payload.get("experiences", []):
        bullets = e.get("bullets", [])
        old_id = e.get("id")
        exp = Experience(profile_id=profile.id, **strip(e, extra={"bullets"}))
        db.add(exp)
        db.flush()
        if old_id is not None:
            id_map[EntityType.EXPERIENCE][old_id] = exp.id
        for b in bullets:
            old_bullet_id = b.get("id")
            bullet_row = ExperienceBullet(experience_id=exp.id, **strip(b, extra={"experience_id"}))
            db.add(bullet_row)
            db.flush()
            if old_bullet_id is not None:
                id_map[EntityType.EXPERIENCE_BULLET][old_bullet_id] = bullet_row.id

    for p in payload.get("projects", []):
        results = p.get("results", [])
        old_id = p.get("id")
        proj = Project(profile_id=profile.id, **strip(p, extra={"results"}))
        db.add(proj)
        db.flush()
        if old_id is not None:
            id_map[EntityType.PROJECT][old_id] = proj.id
        for r in results:
            old_result_id = r.get("id")
            result_row = ProjectResult(project_id=proj.id, **strip(r, extra={"project_id"}))
            db.add(result_row)
            db.flush()
            if old_result_id is not None:
                id_map[EntityType.PROJECT_RESULT][old_result_id] = result_row.id

    for s in payload.get("skills", []):
        old_id = s.get("id")
        row = Skill(profile_id=profile.id, **strip(s))
        db.add(row)
        db.flush()
        if old_id is not None:
            id_map[EntityType.SKILL][old_id] = row.id

    for c in payload.get("certifications", []):
        old_id = c.get("id")
        row = Certification(profile_id=profile.id, **strip(c))
        db.add(row)
        db.flush()
        if old_id is not None:
            id_map[EntityType.CERTIFICATION][old_id] = row.id

    for a in payload.get("achievements", []):
        old_id = a.get("id")
        row = Achievement(profile_id=profile.id, **strip(a))
        db.add(row)
        db.flush()
        if old_id is not None:
            id_map[EntityType.ACHIEVEMENT][old_id] = row.id

    for r in payload.get("research_items", []):
        old_id = r.get("id")
        row = Research(profile_id=profile.id, **strip(r))
        db.add(row)
        db.flush()
        if old_id is not None:
            id_map[EntityType.RESEARCH][old_id] = row.id

    for ev in payload.get("evidence", []):
        links = ev.get("links", [])
        evidence = Evidence(profile_id=profile.id, **strip(ev, extra={"links"}))
        db.add(evidence)
        db.flush()
        for link in links:
            entity_type = EntityType(link["entity_type"])
            old_entity_id = link["entity_id"]
            new_entity_id = id_map[entity_type].get(old_entity_id, old_entity_id)
            db.add(
                EvidenceLink(
                    evidence_id=evidence.id,
                    entity_type=entity_type,
                    entity_id=new_entity_id,
                )
            )

    db.commit()
    db.refresh(profile)
    return profile
