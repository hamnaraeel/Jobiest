from sqlalchemy import Boolean, Enum, Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import ApplicationFieldStatus, ApplicationFieldType
from app.models.mixins import TimestampMixin


class ApplicationField(Base, TimestampMixin):
    """One detected field on one application's form(s). `field_identifier`
    is whatever the page itself exposes (name/id/a stable generated
    selector) -- not guaranteed unique across pages, so lookups always
    scope by application_id + page_url + field_identifier."""

    __tablename__ = "application_fields"

    id: Mapped[int] = mapped_column(primary_key=True)
    application_id: Mapped[int] = mapped_column(ForeignKey("applications.id", ondelete="CASCADE"), nullable=False)

    field_identifier: Mapped[str] = mapped_column(String(500), nullable=False)
    label: Mapped[str | None] = mapped_column(String(500))
    field_type: Mapped[ApplicationFieldType] = mapped_column(
        Enum(ApplicationFieldType, name="application_field_type"), default=ApplicationFieldType.UNKNOWN, nullable=False
    )
    page_url: Mapped[str | None] = mapped_column(String(1000))
    required: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    detected_value: Mapped[str | None] = mapped_column(Text)
    # e.g. "profile.email", "application_answer_123", "user_input" -- see
    # field_mapper.py. Every filled field must be traceable to one of these.
    mapped_source: Mapped[str | None] = mapped_column(String(255))
    proposed_value: Mapped[str | None] = mapped_column(Text)
    final_value: Mapped[str | None] = mapped_column(Text)

    status: Mapped[ApplicationFieldStatus] = mapped_column(
        Enum(ApplicationFieldStatus, name="application_field_status"), default=ApplicationFieldStatus.DETECTED, nullable=False
    )
    confidence: Mapped[float | None] = mapped_column(Float)
    user_review_required: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    application: Mapped["Application"] = relationship(back_populates="fields")
