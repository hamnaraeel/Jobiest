from datetime import datetime

from sqlalchemy import ARRAY, JSON, DateTime, Enum, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import ResumeImportStatus
from app.models.mixins import TimestampMixin


class ResumeImport(Base, TimestampMixin):
    """One uploaded resume and what the AI extracted from it -- a
    proposal, not live profile data, until a human explicitly confirms
    it (see resume_import_service.confirm_import). raw_text is kept so a
    human can compare the extraction against the source when reviewing."""

    __tablename__ = "resume_imports"

    id: Mapped[int] = mapped_column(primary_key=True)
    profile_id: Mapped[int | None] = mapped_column(ForeignKey("career_profiles.id", ondelete="SET NULL"))

    filename: Mapped[str] = mapped_column(String(500), nullable=False)
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    parsed_data: Mapped[dict] = mapped_column(JSON, nullable=False)
    warnings: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)

    status: Mapped[ResumeImportStatus] = mapped_column(
        Enum(ResumeImportStatus, name="resume_import_status"), default=ResumeImportStatus.PENDING_REVIEW, nullable=False, index=True
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    profile: Mapped["CareerProfile | None"] = relationship()
