"""Truth / verification rules for the career knowledge base.

These rules exist so that a future CV / cover-letter generation agent has a
mechanical way to check facts instead of relying on an LLM "being careful":

    1. Never invent a skill, employment, project, job title, degree,
       certification, metric, achievement, or responsibility.
    2. Never change a numerical result.
    3. Never claim a technology or years of experience the profile does
       not support.
    4. If a job requires something the profile does not have, the correct
       output is the status "missing" -- never a fabricated addition.

This module is intentionally pure data-layer logic: it does not call an
LLM. It gives the (future) generation layer the primitives to enforce the
rules above.
"""

from enum import Enum
from typing import Type, TypeVar

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.enums import EntityType
from app.models.evidence import EvidenceLink
from app.models.skill import Skill

SchemaT = TypeVar("SchemaT", bound=BaseModel)


class SkillStatus(str, Enum):
    VERIFIED = "verified"
    UNVERIFIED = "unverified"
    MISSING = "missing"


def orm_kwargs(payload: BaseModel, exclude: set[str] = frozenset(), url_fields: tuple[str, ...] = ()) -> dict:
    """model_dump() in "python" mode leaves Pydantic HttpUrl objects intact,
    which SQLAlchemy's String columns can't bind directly; "json" mode fixes
    that but also turns `date` fields into ISO strings, which is fragile
    for Date columns. This dumps in python mode (safe for dates) and then
    stringifies only the named URL fields."""

    data = payload.model_dump(exclude=exclude)
    for field in url_fields:
        if data.get(field) is not None:
            data[field] = str(data[field])
    return data


def get_evidence_ids(db: Session, entity_type: EntityType, entity_id: int) -> list[int]:
    rows = db.execute(
        select(EvidenceLink.evidence_id).where(
            EvidenceLink.entity_type == entity_type,
            EvidenceLink.entity_id == entity_id,
        )
    ).scalars().all()
    return list(rows)


def to_read_schema(
    db: Session,
    orm_obj,
    schema_cls: Type[SchemaT],
    entity_type: EntityType,
    nested: list[tuple[str, EntityType]] | None = None,
) -> SchemaT:
    """Build a *Read schema from an ORM object, filling in the computed
    `evidence_ids` field (evidence is stored via EvidenceLink, not as a
    column on the entity itself).

    `nested` lets callers also fill in evidence_ids on child collections,
    e.g. Experience.bullets or Project.results, by passing
    [("bullets", EntityType.EXPERIENCE_BULLET)].
    """

    data = schema_cls.model_validate(orm_obj, from_attributes=True)
    updates: dict = {}

    if hasattr(data, "evidence_ids"):
        updates["evidence_ids"] = get_evidence_ids(db, entity_type, orm_obj.id)

    for attr_name, child_entity_type in nested or []:
        children_orm = getattr(orm_obj, attr_name)
        children_data = getattr(data, attr_name)
        new_children = []
        for child_orm, child_data in zip(children_orm, children_data):
            if hasattr(child_data, "evidence_ids"):
                child_data = child_data.model_copy(
                    update={"evidence_ids": get_evidence_ids(db, child_entity_type, child_orm.id)}
                )
            new_children.append(child_data)
        updates[attr_name] = new_children

    if updates:
        data = data.model_copy(update=updates)
    return data


def classify_skill_for_job(db: Session, profile_id: int, required_skill_name: str) -> SkillStatus:
    """Given a skill name a job description requires, classify it against
    the career profile:

    - VERIFIED   -> the profile has this skill and it is marked verified.
    - UNVERIFIED -> the profile has this skill but it is not yet verified
                    (no evidence attached).
    - MISSING    -> the profile does not have this skill at all. The CV
                    agent must NEVER add a missing skill to a tailored CV;
                    it must be surfaced to the user as a gap instead.
    """

    skill = db.execute(
        select(Skill).where(
            Skill.profile_id == profile_id,
            Skill.name.ilike(required_skill_name.strip()),
        )
    ).scalar_one_or_none()

    if skill is None:
        return SkillStatus.MISSING
    return SkillStatus.VERIFIED if skill.verified else SkillStatus.UNVERIFIED


def require_evidence_for_verification(db: Session, entity_type: EntityType, entity_id: int) -> None:
    """Guard used before flipping `verified` to True on any entity: refuse
    unless at least one Evidence row is linked to it."""

    if not get_evidence_ids(db, entity_type, entity_id):
        raise ValueError(
            f"Cannot mark {entity_type.value}:{entity_id} as verified without at least one linked Evidence record."
        )
