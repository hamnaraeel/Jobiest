from datetime import date, datetime

from sqlalchemy import ARRAY, Date, DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import JobEmploymentType, JobStatus, PriorityLevel, WorkplaceType
from app.models.mixins import TimestampMixin


class Job(Base, TimestampMixin):
    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(primary_key=True)

    title: Mapped[str | None] = mapped_column(String(255))
    company: Mapped[str | None] = mapped_column(String(255), index=True)
    location: Mapped[str | None] = mapped_column(String(255))
    employment_type: Mapped[JobEmploymentType | None] = mapped_column(Enum(JobEmploymentType, name="job_employment_type"))
    workplace_type: Mapped[WorkplaceType | None] = mapped_column(Enum(WorkplaceType, name="workplace_type"))

    url: Mapped[str | None] = mapped_column(String(1000))
    canonical_url: Mapped[str | None] = mapped_column(String(1000), index=True)
    description_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    source: Mapped[str | None] = mapped_column(String(255))

    raw_content: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    summary: Mapped[str | None] = mapped_column(Text)
    keywords: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)

    salary_min: Mapped[int | None] = mapped_column(Integer)
    salary_max: Mapped[int | None] = mapped_column(Integer)
    salary_currency: Mapped[str | None] = mapped_column(String(10))

    posted_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    application_deadline: Mapped[date | None] = mapped_column(Date, nullable=True)
    # Where application_deadline came from (e.g. "job posting", "recruiter
    # email") -- never guessed; NULL deadline stays NULL, never invented
    # (spec section 26).
    deadline_source: Mapped[str | None] = mapped_column(String(255))
    extracted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    status: Mapped[JobStatus] = mapped_column(Enum(JobStatus, name="job_status"), default=JobStatus.DISCOVERED, nullable=False, index=True)

    duplicate_of_job_id: Mapped[int | None] = mapped_column(ForeignKey("jobs.id", ondelete="SET NULL"))
    # External ATS/board job id (e.g. a Greenhouse gh_jid), when known --
    # one of the duplicate-detection keys alongside canonical_url and
    # company+normalized-title (spec section 25).
    external_job_id: Mapped[str | None] = mapped_column(String(255), index=True)

    priority: Mapped[PriorityLevel] = mapped_column(Enum(PriorityLevel, name="priority_level"), default=PriorityLevel.MEDIUM, nullable=False)
    tags: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)

    requirements: Mapped[list["JobRequirement"]] = relationship(
        back_populates="job", cascade="all, delete-orphan", foreign_keys="JobRequirement.job_id"
    )
    match: Mapped["JobMatch | None"] = relationship(back_populates="job", cascade="all, delete-orphan", uselist=False)
    applications: Mapped[list["Application"]] = relationship(back_populates="job", cascade="all, delete-orphan")
    notes: Mapped[list["JobNote"]] = relationship(back_populates="job", cascade="all, delete-orphan", order_by="JobNote.created_at")
