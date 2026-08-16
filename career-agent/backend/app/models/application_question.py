from sqlalchemy import Boolean, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import ApplicationQuestionType
from app.models.mixins import TimestampMixin


class ApplicationQuestion(Base, TimestampMixin):
    __tablename__ = "application_questions"

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False)

    question: Mapped[str] = mapped_column(Text, nullable=False)
    question_type: Mapped[ApplicationQuestionType] = mapped_column(
        Enum(ApplicationQuestionType, name="application_question_type"),
        default=ApplicationQuestionType.UNKNOWN, nullable=False,
    )
    character_limit: Mapped[int | None] = mapped_column(Integer)
    word_limit: Mapped[int | None] = mapped_column(Integer)
    required: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    job: Mapped["Job"] = relationship()
    answers: Mapped[list["ApplicationAnswer"]] = relationship(back_populates="question", cascade="all, delete-orphan")
