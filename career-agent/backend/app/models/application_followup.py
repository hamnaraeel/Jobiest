from datetime import date, datetime

from sqlalchemy import Date, DateTime, Enum, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import FollowUpStatus, FollowUpType
from app.models.mixins import TimestampMixin


class ApplicationFollowUp(Base, TimestampMixin):
    """A follow-up task tied to one application -- e.g. "email the
    recruiter a week after submitting." Purely a reminder/tracking record:
    nothing here ever sends a message on its own (spec section 11)."""

    __tablename__ = "application_followups"

    id: Mapped[int] = mapped_column(primary_key=True)
    application_id: Mapped[int] = mapped_column(ForeignKey("applications.id", ondelete="CASCADE"), nullable=False)

    due_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    type: Mapped[FollowUpType] = mapped_column(Enum(FollowUpType, name="followup_type"), default=FollowUpType.CUSTOM, nullable=False)
    subject: Mapped[str | None] = mapped_column(String(500))
    notes: Mapped[str | None] = mapped_column(Text)
    status: Mapped[FollowUpStatus] = mapped_column(Enum(FollowUpStatus, name="followup_status"), default=FollowUpStatus.PENDING, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    application: Mapped["Application"] = relationship(back_populates="followups")
