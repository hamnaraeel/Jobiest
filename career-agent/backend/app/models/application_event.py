from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, Enum, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import ApplicationEventType


class ApplicationEvent(Base):
    """Append-only audit log for one application -- every action the
    agent takes, in order. Never edited or deleted; this is what makes
    the whole assisted-application process reviewable after the fact."""

    __tablename__ = "application_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    application_id: Mapped[int] = mapped_column(ForeignKey("applications.id", ondelete="CASCADE"), nullable=False)

    event_type: Mapped[ApplicationEventType] = mapped_column(Enum(ApplicationEventType, name="application_event_type"), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    event_metadata: Mapped[dict] = mapped_column(JSON, default=dict)

    application: Mapped["Application"] = relationship(back_populates="events")
