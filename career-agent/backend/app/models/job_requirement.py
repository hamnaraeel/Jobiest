from sqlalchemy import Boolean, Enum, Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import RequirementCategory, RequirementImportance
from app.models.mixins import TimestampMixin


class JobRequirement(Base, TimestampMixin):
    __tablename__ = "job_requirements"

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False)

    requirement_text: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[RequirementCategory] = mapped_column(Enum(RequirementCategory, name="requirement_category"), nullable=False)
    importance: Mapped[RequirementImportance] = mapped_column(
        Enum(RequirementImportance, name="requirement_importance"), default=RequirementImportance.MEDIUM, nullable=False
    )
    required: Mapped[bool] = mapped_column(Boolean, nullable=False)

    skill_name: Mapped[str | None] = mapped_column(String(255))
    years_required: Mapped[float | None] = mapped_column(Float)
    education_requirement: Mapped[str | None] = mapped_column(String(500))
    evidence_required: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    job: Mapped["Job"] = relationship(back_populates="requirements", foreign_keys=[job_id])
