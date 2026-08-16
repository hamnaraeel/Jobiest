from datetime import datetime, timezone

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import ApplicationStatus


class ApplicationStatusHistory(Base):
    """Append-only record of every status transition an Application has
    gone through. Never overwritten or deleted -- this is what lets the
    full submitted -> under_review -> interview -> ... -> rejected chain
    stay visible after the fact, instead of only ever showing the current
    status."""

    __tablename__ = "application_status_history"

    id: Mapped[int] = mapped_column(primary_key=True)
    application_id: Mapped[int] = mapped_column(ForeignKey("applications.id", ondelete="CASCADE"), nullable=False)

    old_status: Mapped[ApplicationStatus | None] = mapped_column(Enum(ApplicationStatus, name="application_status"))
    new_status: Mapped[ApplicationStatus] = mapped_column(Enum(ApplicationStatus, name="application_status"), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)
    # e.g. "user" (manual PATCH) or "system" (Step 5 auto-marking submitted).
    source: Mapped[str] = mapped_column(String(50), default="user", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    application: Mapped["Application"] = relationship(back_populates="status_history")
