from datetime import date

from pgvector.sqlalchemy import Vector
from sqlalchemy import ARRAY, Boolean, Date, Enum, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import EmploymentType
from app.models.mixins import EMBEDDING_DIM, TimestampMixin, VerifiableMixin


class Experience(Base, TimestampMixin, VerifiableMixin):
    __tablename__ = "experiences"

    id: Mapped[int] = mapped_column(primary_key=True)
    profile_id: Mapped[int] = mapped_column(ForeignKey("career_profiles.id", ondelete="CASCADE"), nullable=False)

    company: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(255), nullable=False)
    employment_type: Mapped[EmploymentType | None] = mapped_column(Enum(EmploymentType, name="employment_type"))
    location: Mapped[str | None] = mapped_column(String(255))
    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    currently_working: Mapped[bool] = mapped_column(Boolean, default=False)
    description: Mapped[str | None] = mapped_column(Text)
    technologies: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    skills: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    achievements: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)

    profile: Mapped["CareerProfile"] = relationship(back_populates="experiences")
    bullets: Mapped[list["ExperienceBullet"]] = relationship(
        back_populates="experience", cascade="all, delete-orphan"
    )


class ExperienceBullet(Base, TimestampMixin, VerifiableMixin):
    """Each bullet is stored independently so a future CV agent can pick
    only the bullets relevant to a specific job, instead of whole blocks."""

    __tablename__ = "experience_bullets"

    id: Mapped[int] = mapped_column(primary_key=True)
    experience_id: Mapped[int] = mapped_column(ForeignKey("experiences.id", ondelete="CASCADE"), nullable=False)

    bullet: Mapped[str] = mapped_column(Text, nullable=False)
    skills: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)

    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIM), nullable=True)

    experience: Mapped["Experience"] = relationship(back_populates="bullets")
