from pgvector.sqlalchemy import Vector
from sqlalchemy import Enum, Float, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import ProficiencyLevel, SkillCategory
from app.models.mixins import EMBEDDING_DIM, TimestampMixin, VerifiableMixin


class Skill(Base, TimestampMixin, VerifiableMixin):
    __tablename__ = "skills"
    __table_args__ = (UniqueConstraint("profile_id", "name", name="uq_skill_profile_name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    profile_id: Mapped[int] = mapped_column(ForeignKey("career_profiles.id", ondelete="CASCADE"), nullable=False)

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[SkillCategory] = mapped_column(Enum(SkillCategory, name="skill_category"), nullable=False)
    proficiency: Mapped[ProficiencyLevel | None] = mapped_column(
        Enum(ProficiencyLevel, name="proficiency_level")
    )
    years_used: Mapped[float | None] = mapped_column(Float)

    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIM), nullable=True)

    profile: Mapped["CareerProfile"] = relationship(back_populates="skills")
