from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import InterviewStatus, InterviewType
from app.models.mixins import TimestampMixin


class Interview(Base, TimestampMixin):
    """One interview round for one application. Only ever populated from
    what the user (or a verified source, e.g. a future calendar
    integration) actually supplies -- never assumed or invented (spec
    section 13)."""

    __tablename__ = "interviews"

    id: Mapped[int] = mapped_column(primary_key=True)
    application_id: Mapped[int] = mapped_column(ForeignKey("applications.id", ondelete="CASCADE"), nullable=False)

    type: Mapped[InterviewType] = mapped_column(Enum(InterviewType, name="interview_type"), default=InterviewType.OTHER, nullable=False)
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    duration_minutes: Mapped[int | None] = mapped_column(Integer)
    location: Mapped[str | None] = mapped_column(String(500))
    meeting_url: Mapped[str | None] = mapped_column(String(1000))
    interviewer: Mapped[str | None] = mapped_column(String(255))
    notes: Mapped[str | None] = mapped_column(Text)
    status: Mapped[InterviewStatus] = mapped_column(Enum(InterviewStatus, name="interview_status"), default=InterviewStatus.SCHEDULED, nullable=False)

    application: Mapped["Application"] = relationship(back_populates="interviews")
