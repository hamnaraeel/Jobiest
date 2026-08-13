from sqlalchemy import Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import EntityType, SourceType
from app.models.mixins import TimestampMixin


class Evidence(Base, TimestampMixin):
    """A verifiable source backing a career claim (a CV, a GitHub repo, a
    certificate, etc). Facts are only allowed to be `verified=True` once
    they are linked to at least one Evidence row via EvidenceLink."""

    __tablename__ = "evidence"

    id: Mapped[int] = mapped_column(primary_key=True)
    profile_id: Mapped[int] = mapped_column(ForeignKey("career_profiles.id", ondelete="CASCADE"), nullable=False)

    source_type: Mapped[SourceType] = mapped_column(Enum(SourceType, name="source_type"), nullable=False)
    source_name: Mapped[str] = mapped_column(String(255), nullable=False)
    source_url: Mapped[str | None] = mapped_column(String(500))
    description: Mapped[str | None] = mapped_column(Text)
    verified: Mapped[bool] = mapped_column(default=False, nullable=False)

    profile: Mapped["CareerProfile"] = relationship(back_populates="evidence_items")
    links: Mapped[list["EvidenceLink"]] = relationship(back_populates="evidence", cascade="all, delete-orphan")


class EvidenceLink(Base):
    """Generic many-to-many join between Evidence and any career-fact entity
    (skill, experience_bullet, project, project_result, research,
    certification, achievement, education). Using one generic link table
    instead of an evidence_ids array column on every entity keeps evidence
    referential-integrity in one place."""

    __tablename__ = "evidence_links"

    id: Mapped[int] = mapped_column(primary_key=True)
    evidence_id: Mapped[int] = mapped_column(ForeignKey("evidence.id", ondelete="CASCADE"), nullable=False)
    entity_type: Mapped[EntityType] = mapped_column(Enum(EntityType, name="entity_type"), nullable=False)
    entity_id: Mapped[int] = mapped_column(Integer, nullable=False)

    evidence: Mapped["Evidence"] = relationship(back_populates="links")
