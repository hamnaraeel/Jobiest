from sqlalchemy import Boolean, Enum, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import CVSectionType
from app.models.mixins import TimestampMixin


class CVSection(Base, TimestampMixin):
    """Tracks which sections a CV version includes and in what order --
    the AI is explicitly allowed to reorder sections, so that decision
    needs to be recorded somewhere auditable rather than only implied by
    array order inside a JSON blob. The section's actual content lives on
    CVVersion (skills/experience/projects/...); this table is the ordering
    + inclusion record, not a content duplicate."""

    __tablename__ = "cv_sections"

    id: Mapped[int] = mapped_column(primary_key=True)
    cv_version_id: Mapped[int] = mapped_column(ForeignKey("cv_versions.id", ondelete="CASCADE"), nullable=False)

    section_type: Mapped[CVSectionType] = mapped_column(Enum(CVSectionType, name="cv_section_type"), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False)
    included: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    cv_version: Mapped["CVVersion"] = relationship(back_populates="sections")
