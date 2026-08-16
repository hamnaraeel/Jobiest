from sqlalchemy import ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin


class JobNote(Base, TimestampMixin):
    """Free-form note tied to one job (e.g. "Strong match but requires
    relocation."). Never modifies the Career Profile or the job's own
    extracted data -- purely an observation the user records for
    themselves (spec section 16)."""

    __tablename__ = "job_notes"

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False)

    content: Mapped[str] = mapped_column(Text, nullable=False)

    job: Mapped["Job"] = relationship(back_populates="notes")
