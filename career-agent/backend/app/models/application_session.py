from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import ApplicationSessionStatus


class ApplicationSession(Base):
    """One real browser session backing an Application. Deliberately holds
    no credentials of any kind -- see browser/browser_manager.py, which
    never automates login, and the security rules in
    docs/browser-application-assistant.md."""

    __tablename__ = "application_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    application_id: Mapped[int] = mapped_column(ForeignKey("applications.id", ondelete="CASCADE"), nullable=False)

    browser: Mapped[str] = mapped_column(String(50), nullable=False, default="chromium")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    current_url: Mapped[str | None] = mapped_column(String(1000))
    status: Mapped[ApplicationSessionStatus] = mapped_column(
        Enum(ApplicationSessionStatus, name="application_session_status"), default=ApplicationSessionStatus.ACTIVE, nullable=False
    )
    error_message: Mapped[str | None] = mapped_column(Text)

    application: Mapped["Application"] = relationship(back_populates="sessions")
