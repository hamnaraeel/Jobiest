from datetime import date

from sqlalchemy import Date, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import OfferStatus
from app.models.mixins import TimestampMixin


class Offer(Base, TimestampMixin):
    """A job offer tied to one application. Salary/terms are only ever
    what the user actually enters -- never inferred or estimated (spec
    section 14)."""

    __tablename__ = "offers"

    id: Mapped[int] = mapped_column(primary_key=True)
    application_id: Mapped[int] = mapped_column(ForeignKey("applications.id", ondelete="CASCADE"), nullable=False)

    company: Mapped[str | None] = mapped_column(String(255))
    role: Mapped[str | None] = mapped_column(String(255))
    salary: Mapped[int | None] = mapped_column(Integer)
    currency: Mapped[str | None] = mapped_column(String(10))
    employment_type: Mapped[str | None] = mapped_column(String(100))
    location: Mapped[str | None] = mapped_column(String(255))
    start_date: Mapped[date | None] = mapped_column(Date)
    notes: Mapped[str | None] = mapped_column(Text)
    status: Mapped[OfferStatus] = mapped_column(Enum(OfferStatus, name="offer_status"), default=OfferStatus.RECEIVED, nullable=False)

    application: Mapped["Application"] = relationship(back_populates="offers")
