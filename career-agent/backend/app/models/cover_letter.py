from sqlalchemy import JSON, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import ApplicationMaterialStatus
from app.models.mixins import TimestampMixin


class CoverLetter(Base, TimestampMixin):
    """One tailored cover letter for one job. Never overwritten -- each
    generation/regeneration creates a new row with an incremented
    version_number, exactly like CVVersion."""

    __tablename__ = "cover_letters"

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False)
    cv_version_id: Mapped[int] = mapped_column(ForeignKey("cv_versions.id", ondelete="CASCADE"), nullable=False)
    profile_id: Mapped[int] = mapped_column(ForeignKey("career_profiles.id", ondelete="CASCADE"), nullable=False)

    version_name: Mapped[str] = mapped_column(String(255), nullable=False)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    word_count: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[ApplicationMaterialStatus] = mapped_column(
        Enum(ApplicationMaterialStatus, name="cv_status"), default=ApplicationMaterialStatus.DRAFT, nullable=False
    )

    # List of {source_type, source_id} -- every verified profile item that
    # was given to the generator as context, i.e. everything the letter
    # could truthfully have drawn from. See docs/cover-letters.md.
    source_evidence: Mapped[list] = mapped_column(JSON, default=list)
    warnings: Mapped[list] = mapped_column(JSON, default=list)

    pdf_path: Mapped[str | None] = mapped_column(String(1000))

    job: Mapped["Job"] = relationship()
    cv_version: Mapped["CVVersion"] = relationship()
    profile: Mapped["CareerProfile"] = relationship()
