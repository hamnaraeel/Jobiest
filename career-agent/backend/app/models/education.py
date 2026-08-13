from datetime import date

from pgvector.sqlalchemy import Vector
from sqlalchemy import ARRAY, Date, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import EMBEDDING_DIM, TimestampMixin, VerifiableMixin


class Education(Base, TimestampMixin, VerifiableMixin):
    __tablename__ = "educations"

    id: Mapped[int] = mapped_column(primary_key=True)
    profile_id: Mapped[int] = mapped_column(ForeignKey("career_profiles.id", ondelete="CASCADE"), nullable=False)

    institution: Mapped[str] = mapped_column(String(255), nullable=False)
    degree: Mapped[str] = mapped_column(String(255), nullable=False)
    field: Mapped[str | None] = mapped_column(String(255))
    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    location: Mapped[str | None] = mapped_column(String(255))
    grade: Mapped[str | None] = mapped_column(String(100))
    relevant_coursework: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    thesis: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)

    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIM), nullable=True)

    profile: Mapped["CareerProfile"] = relationship(back_populates="educations")
