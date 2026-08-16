from sqlalchemy import JSON, Enum, ForeignKey, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import ApplicationMaterialStatus
from app.models.mixins import TimestampMixin


class ApplicationAnswer(Base, TimestampMixin):
    __tablename__ = "application_answers"

    id: Mapped[int] = mapped_column(primary_key=True)
    question_id: Mapped[int] = mapped_column(ForeignKey("application_questions.id", ondelete="CASCADE"), nullable=False)

    answer: Mapped[str] = mapped_column(Text, nullable=False)
    word_count: Mapped[int] = mapped_column(Integer, nullable=False)
    character_count: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[ApplicationMaterialStatus] = mapped_column(
        Enum(ApplicationMaterialStatus, name="cv_status"), default=ApplicationMaterialStatus.DRAFT, nullable=False
    )

    # List of {source_type, source_id} -- same meaning as
    # CoverLetter.source_evidence.
    evidence: Mapped[list] = mapped_column(JSON, default=list)
    warnings: Mapped[list] = mapped_column(JSON, default=list)

    question: Mapped["ApplicationQuestion"] = relationship(back_populates="answers")
