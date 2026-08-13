from datetime import date

from sqlalchemy import ARRAY, Date, Enum, Float, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import RemotePreference
from app.models.mixins import TimestampMixin


class CareerProfile(Base, TimestampMixin):
    __tablename__ = "career_profiles"

    id: Mapped[int] = mapped_column(primary_key=True)

    # Personal information
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    professional_title: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    phone: Mapped[str | None] = mapped_column(String(50))
    city: Mapped[str | None] = mapped_column(String(100))
    country: Mapped[str | None] = mapped_column(String(100))
    linkedin_url: Mapped[str | None] = mapped_column(String(500))
    github_url: Mapped[str | None] = mapped_column(String(500))
    portfolio_url: Mapped[str | None] = mapped_column(String(500))

    # Professional summary
    current_summary: Mapped[str | None] = mapped_column(Text)
    target_roles: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    preferred_industries: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    preferred_locations: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    remote_preference: Mapped[RemotePreference | None] = mapped_column(Enum(RemotePreference, name="remote_preference"))
    years_of_experience: Mapped[float | None] = mapped_column(Float)

    educations: Mapped[list["Education"]] = relationship(back_populates="profile", cascade="all, delete-orphan")
    experiences: Mapped[list["Experience"]] = relationship(back_populates="profile", cascade="all, delete-orphan")
    projects: Mapped[list["Project"]] = relationship(back_populates="profile", cascade="all, delete-orphan")
    skills: Mapped[list["Skill"]] = relationship(back_populates="profile", cascade="all, delete-orphan")
    certifications: Mapped[list["Certification"]] = relationship(back_populates="profile", cascade="all, delete-orphan")
    achievements: Mapped[list["Achievement"]] = relationship(back_populates="profile", cascade="all, delete-orphan")
    research_items: Mapped[list["Research"]] = relationship(back_populates="profile", cascade="all, delete-orphan")
    evidence_items: Mapped[list["Evidence"]] = relationship(back_populates="profile", cascade="all, delete-orphan")
