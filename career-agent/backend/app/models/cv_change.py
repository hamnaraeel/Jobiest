from sqlalchemy import Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import CVChangeType, CVSectionType, EntityType
from app.models.mixins import TimestampMixin


class CVChange(Base, TimestampMixin):
    """One row per change the customization made relative to the source
    Career Profile -- the basis for GET /cvs/{id}/comparison and for a
    human reviewer to see exactly what was added, dropped, reworded, or
    reordered before approving a CV."""

    __tablename__ = "cv_changes"

    id: Mapped[int] = mapped_column(primary_key=True)
    cv_version_id: Mapped[int] = mapped_column(ForeignKey("cv_versions.id", ondelete="CASCADE"), nullable=False)

    change_type: Mapped[CVChangeType] = mapped_column(Enum(CVChangeType, name="cv_change_type"), nullable=False)
    section: Mapped[CVSectionType] = mapped_column(Enum(CVSectionType, name="cv_section_type"), nullable=False)

    original_text: Mapped[str | None] = mapped_column(Text)
    customized_text: Mapped[str | None] = mapped_column(Text)

    source_type: Mapped[EntityType | None] = mapped_column(Enum(EntityType, name="entity_type"))
    source_id: Mapped[str | None] = mapped_column(String(255))
    reason: Mapped[str | None] = mapped_column(Text)

    cv_version: Mapped["CVVersion"] = relationship(back_populates="changes")
