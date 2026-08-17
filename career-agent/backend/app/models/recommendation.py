from datetime import datetime

from sqlalchemy import JSON, DateTime, Enum, Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import PriorityLevel, RecommendationStatus, RecommendationType
from app.models.mixins import TimestampMixin


class Recommendation(Base, TimestampMixin):
    """One piece of advice from the Step 7 intelligence layer. Always
    carries its own reasoning -- title/description are the WHAT and WHY,
    `evidence` is the concrete numbers it's based on, `confidence` (with
    `confidence_reason`) says how much weight it deserves, and `action`
    is what the user could do about it. Never auto-applied: nothing in
    this codebase changes Application/Job/CareerProfile state just
    because a Recommendation exists -- the user decides via the
    accept/dismiss/complete endpoints (spec sections 5, 57-59)."""

    __tablename__ = "recommendations"

    id: Mapped[int] = mapped_column(primary_key=True)

    type: Mapped[RecommendationType] = mapped_column(Enum(RecommendationType, name="recommendation_type"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    priority: Mapped[PriorityLevel] = mapped_column(Enum(PriorityLevel, name="priority_level"), default=PriorityLevel.MEDIUM, nullable=False)

    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    confidence_reason: Mapped[str] = mapped_column(Text, nullable=False)

    # The concrete numbers/facts this recommendation is based on -- e.g.
    # {"applications": 15, "interviews": 5, "rate": 0.33}. Every insight
    # must be traceable back to this (spec section 44).
    evidence: Mapped[dict] = mapped_column(JSON, default=dict)
    action: Mapped[str | None] = mapped_column(Text)

    related_job_id: Mapped[int | None] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"))
    related_application_id: Mapped[int | None] = mapped_column(ForeignKey("applications.id", ondelete="CASCADE"))

    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[RecommendationStatus] = mapped_column(
        Enum(RecommendationStatus, name="recommendation_status"), default=RecommendationStatus.NEW, nullable=False, index=True
    )

    related_job: Mapped["Job | None"] = relationship()
    related_application: Mapped["Application | None"] = relationship()
