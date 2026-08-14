from sqlalchemy import JSON, Enum, ForeignKey, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import Recommendation
from app.models.mixins import TimestampMixin


class JobMatch(Base, TimestampMixin):
    """The current match result for a job. Re-running POST /jobs/{id}/match
    updates this row in place rather than appending a new one -- a job has
    one current recommendation, not a growing history, which keeps the
    dashboard filters (GET /jobs?min_score=...) a plain join."""

    __tablename__ = "job_matches"

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, unique=True)

    overall_score: Mapped[int] = mapped_column(Integer, nullable=False)
    recommendation: Mapped[Recommendation] = mapped_column(Enum(Recommendation, name="recommendation"), nullable=False)

    matched_requirements: Mapped[list] = mapped_column(JSON, default=list)
    partial_requirements: Mapped[list] = mapped_column(JSON, default=list)
    missing_requirements: Mapped[list] = mapped_column(JSON, default=list)
    unknown_requirements: Mapped[list] = mapped_column(JSON, default=list)
    critical_gaps: Mapped[list] = mapped_column(JSON, default=list)

    strengths: Mapped[list] = mapped_column(JSON, default=list)
    weaknesses: Mapped[list] = mapped_column(JSON, default=list)
    reasoning_summary: Mapped[str | None] = mapped_column(Text)

    job: Mapped["Job"] = relationship(back_populates="match")
