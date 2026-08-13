from pgvector.sqlalchemy import Vector
from sqlalchemy import ARRAY, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import EMBEDDING_DIM, TimestampMixin, VerifiableMixin


class Research(Base, TimestampMixin, VerifiableMixin):
    """Research work that is not traditional employment (e.g. thesis work,
    independent research, lab projects)."""

    __tablename__ = "research_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    profile_id: Mapped[int] = mapped_column(ForeignKey("career_profiles.id", ondelete="CASCADE"), nullable=False)

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    methodology: Mapped[str | None] = mapped_column(Text)
    datasets: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    models: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    results: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    publications: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    research_area: Mapped[str | None] = mapped_column(String(255))
    technologies: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)

    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIM), nullable=True)

    profile: Mapped["CareerProfile"] = relationship(back_populates="research_items")
