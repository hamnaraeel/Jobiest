from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import ApplicationPlatform, ApplicationStatus
from app.models.mixins import TimestampMixin


class Application(Base, TimestampMixin):
    """One browser-assisted application attempt for one job. This is an
    ASSISTED workflow record, not an autonomous one -- see
    `submission_approved`, which only POST /applications/{id}/approve-
    submission can ever set to True, and which submission_guard.py checks
    again immediately before any click on a real submit button."""

    __tablename__ = "applications"

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False)
    cv_version_id: Mapped[int | None] = mapped_column(ForeignKey("cv_versions.id", ondelete="SET NULL"))
    cover_letter_id: Mapped[int | None] = mapped_column(ForeignKey("cover_letters.id", ondelete="SET NULL"))

    # A job's own URL and the URL actually used to apply are frequently
    # different (e.g. a job board listing vs. the employer's own ATS).
    original_job_url: Mapped[str | None] = mapped_column(String(1000))
    application_url: Mapped[str | None] = mapped_column(String(1000))
    platform: Mapped[ApplicationPlatform] = mapped_column(
        Enum(ApplicationPlatform, name="application_platform"), default=ApplicationPlatform.UNKNOWN, nullable=False
    )

    status: Mapped[ApplicationStatus] = mapped_column(
        Enum(ApplicationStatus, name="application_status"), default=ApplicationStatus.NOT_STARTED, nullable=False
    )

    # The one gate submission_guard.py checks. Never set by anything other
    # than the explicit approval endpoint.
    submission_approved: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    confirmation_reference: Mapped[str | None] = mapped_column(String(500))

    job: Mapped["Job"] = relationship()
    cv_version: Mapped["CVVersion | None"] = relationship()
    cover_letter: Mapped["CoverLetter | None"] = relationship()
    events: Mapped[list["ApplicationEvent"]] = relationship(
        back_populates="application", cascade="all, delete-orphan", order_by="ApplicationEvent.timestamp"
    )
    fields: Mapped[list["ApplicationField"]] = relationship(back_populates="application", cascade="all, delete-orphan")
    sessions: Mapped[list["ApplicationSession"]] = relationship(back_populates="application", cascade="all, delete-orphan")
