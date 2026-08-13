from datetime import date

from pgvector.sqlalchemy import Vector
from sqlalchemy import ARRAY, Date, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import EMBEDDING_DIM, TimestampMixin, VerifiableMixin


class Project(Base, TimestampMixin, VerifiableMixin):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(primary_key=True)
    profile_id: Mapped[int] = mapped_column(ForeignKey("career_profiles.id", ondelete="CASCADE"), nullable=False)

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    problem: Mapped[str | None] = mapped_column(Text)
    solution: Mapped[str | None] = mapped_column(Text)
    technologies: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    skills: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    github_url: Mapped[str | None] = mapped_column(String(500))
    demo_url: Mapped[str | None] = mapped_column(String(500))
    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)

    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIM), nullable=True)

    profile: Mapped["CareerProfile"] = relationship(back_populates="projects")
    results: Mapped[list["ProjectResult"]] = relationship(back_populates="project", cascade="all, delete-orphan")


class ProjectResult(Base, TimestampMixin, VerifiableMixin):
    """Quantified results are stored one-per-row (separate from the project's
    free-text description) so the CV agent can select individual, verifiable
    metrics rather than paraphrasing numbers out of prose."""

    __tablename__ = "project_results"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)

    description: Mapped[str] = mapped_column(Text, nullable=False)
    metric: Mapped[str | None] = mapped_column(String(255))

    project: Mapped["Project"] = relationship(back_populates="results")
