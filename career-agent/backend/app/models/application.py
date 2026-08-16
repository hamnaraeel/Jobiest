from datetime import datetime

from sqlalchemy import ARRAY, JSON, Boolean, DateTime, Enum, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import ApplicationPlatform, ApplicationStatus, PriorityLevel
from app.models.mixins import TimestampMixin, utcnow


class Application(Base, TimestampMixin):
    """One browser-assisted application attempt for one job. This is an
    ASSISTED workflow record, not an autonomous one -- see
    `submission_approved`, which only POST /applications/{id}/approve-
    submission can ever set to True, and which submission_guard.py checks
    again immediately before any click on a real submit button."""

    __tablename__ = "applications"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Overrides TimestampMixin's created_at to add an index -- applications
    # are commonly listed/sorted by recency (spec section 76).
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False, index=True)

    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, index=True)
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
        Enum(ApplicationStatus, name="application_status"), default=ApplicationStatus.NOT_STARTED, nullable=False, index=True
    )

    # The one gate submission_guard.py checks. Never set by anything other
    # than the explicit approval endpoint.
    submission_approved: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    confirmation_reference: Mapped[str | None] = mapped_column(String(500))

    # --- Step 6: job-search tracking -----------------------------------
    priority: Mapped[PriorityLevel] = mapped_column(Enum(PriorityLevel, name="priority_level"), default=PriorityLevel.MEDIUM, nullable=False, index=True)
    tags: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    # Where this specific application was submitted from (LinkedIn,
    # Indeed, company website, referral, ...) -- distinct from
    # `platform`, which is the *detected ATS* the browser assistant saw.
    source: Mapped[str | None] = mapped_column(String(100))
    # Soft-delete flag: archived applications are never deleted, just
    # hidden from default listings (spec section 53). Independent of
    # `status`, which keeps recording the real outcome (rejected/closed/...).
    archived: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Frozen copy of everything that mattered at submission time (CV/cover
    # letter content, answers, match score, job description, application
    # URL) -- the job or CV can change later, but a submitted application
    # must stay historically accurate to what was actually sent (spec
    # section 22). Populated once, by tracking_service on confirmed
    # submission; never overwritten afterward.
    material_snapshot: Mapped[dict | None] = mapped_column(JSON)

    job: Mapped["Job"] = relationship(back_populates="applications")
    cv_version: Mapped["CVVersion | None"] = relationship()
    cover_letter: Mapped["CoverLetter | None"] = relationship()
    events: Mapped[list["ApplicationEvent"]] = relationship(
        back_populates="application", cascade="all, delete-orphan", order_by="ApplicationEvent.timestamp"
    )
    fields: Mapped[list["ApplicationField"]] = relationship(back_populates="application", cascade="all, delete-orphan")
    sessions: Mapped[list["ApplicationSession"]] = relationship(back_populates="application", cascade="all, delete-orphan")
    status_history: Mapped[list["ApplicationStatusHistory"]] = relationship(
        back_populates="application", cascade="all, delete-orphan", order_by="ApplicationStatusHistory.created_at"
    )
    followups: Mapped[list["ApplicationFollowUp"]] = relationship(
        back_populates="application", cascade="all, delete-orphan", order_by="ApplicationFollowUp.due_date"
    )
    interviews: Mapped[list["Interview"]] = relationship(back_populates="application", cascade="all, delete-orphan")
    offers: Mapped[list["Offer"]] = relationship(back_populates="application", cascade="all, delete-orphan")
    notes: Mapped[list["ApplicationNote"]] = relationship(
        back_populates="application", cascade="all, delete-orphan", order_by="ApplicationNote.created_at"
    )
