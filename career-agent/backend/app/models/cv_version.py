from sqlalchemy import JSON, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import CVStatus
from app.models.mixins import TimestampMixin


class CVVersion(Base, TimestampMixin):
    """One tailored CV for one job. Never overwritten -- each generation
    creates a new row with an incremented version_number, so a job can
    accumulate V1, V2, V3... and every past version stays inspectable."""

    __tablename__ = "cv_versions"

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False)
    profile_id: Mapped[int] = mapped_column(ForeignKey("career_profiles.id", ondelete="CASCADE"), nullable=False)

    version_name: Mapped[str] = mapped_column(String(255), nullable=False)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    template_name: Mapped[str] = mapped_column(String(255), nullable=False, default="ats/ml_engineer")
    status: Mapped[CVStatus] = mapped_column(Enum(CVStatus, name="cv_status"), default=CVStatus.DRAFT, nullable=False)

    # Structured, source-traceable content. Each list entry generally
    # follows the CVBullet shape {text, source_type, source_id, verified}
    # documented in schemas/cv.py -- stored here as plain JSON so the full
    # rendered CV can be read back in one row without joining CVSection.
    summary: Mapped[str | None] = mapped_column(Text)
    skills: Mapped[list] = mapped_column(JSON, default=list)
    experience: Mapped[list] = mapped_column(JSON, default=list)
    projects: Mapped[list] = mapped_column(JSON, default=list)
    education: Mapped[list] = mapped_column(JSON, default=list)
    certifications: Mapped[list] = mapped_column(JSON, default=list)
    research: Mapped[list] = mapped_column(JSON, default=list)
    achievements: Mapped[list] = mapped_column(JSON, default=list)

    latex_source: Mapped[str | None] = mapped_column(Text)
    pdf_path: Mapped[str | None] = mapped_column(String(1000))

    match_score_before: Mapped[int | None] = mapped_column(Integer)
    match_score_after: Mapped[int | None] = mapped_column(Integer)

    # Validation findings that survived the correction retry -- e.g. an
    # unsupported claim that had to be stripped rather than shipped.
    # Non-empty warnings keep status from ever reaching "validated".
    warnings: Mapped[list] = mapped_column(JSON, default=list)

    job: Mapped["Job"] = relationship()
    profile: Mapped["CareerProfile"] = relationship()
    sections: Mapped[list["CVSection"]] = relationship(
        back_populates="cv_version", cascade="all, delete-orphan", order_by="CVSection.sort_order"
    )
    changes: Mapped[list["CVChange"]] = relationship(back_populates="cv_version", cascade="all, delete-orphan")
