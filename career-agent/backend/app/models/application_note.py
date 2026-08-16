from sqlalchemy import Enum, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import ApplicationNoteType
from app.models.mixins import TimestampMixin


class ApplicationNote(Base, TimestampMixin):
    """Free-form note tied to one application. Never modifies the Career
    Profile or any other record -- purely an observation the user records
    for themselves (spec section 15)."""

    __tablename__ = "application_notes"

    id: Mapped[int] = mapped_column(primary_key=True)
    application_id: Mapped[int] = mapped_column(ForeignKey("applications.id", ondelete="CASCADE"), nullable=False)

    content: Mapped[str] = mapped_column(Text, nullable=False)
    note_type: Mapped[ApplicationNoteType] = mapped_column(
        Enum(ApplicationNoteType, name="application_note_type"), default=ApplicationNoteType.GENERAL, nullable=False
    )

    application: Mapped["Application"] = relationship(back_populates="notes")
