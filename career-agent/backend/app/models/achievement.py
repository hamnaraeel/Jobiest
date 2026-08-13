from datetime import date as date_type

from sqlalchemy import Date, Enum, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import AchievementCategory
from app.models.mixins import TimestampMixin, VerifiableMixin


class Achievement(Base, TimestampMixin, VerifiableMixin):
    __tablename__ = "achievements"

    id: Mapped[int] = mapped_column(primary_key=True)
    profile_id: Mapped[int] = mapped_column(ForeignKey("career_profiles.id", ondelete="CASCADE"), nullable=False)

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    date: Mapped[date_type | None] = mapped_column(Date, nullable=True)
    category: Mapped[AchievementCategory] = mapped_column(
        Enum(AchievementCategory, name="achievement_category"), nullable=False
    )
    metric: Mapped[str | None] = mapped_column(String(255))

    profile: Mapped["CareerProfile"] = relationship(back_populates="achievements")
