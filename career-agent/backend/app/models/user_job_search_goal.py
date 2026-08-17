from sqlalchemy import ARRAY, Enum, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.enums import RemotePreference
from app.models.mixins import TimestampMixin


class UserJobSearchGoal(Base, TimestampMixin):
    """The user's own configured job-search targets -- never inferred or
    assumed (spec section 35). Single-user system: goal_service reads the
    most recent row, mirroring CareerProfile's get_default_profile()
    pattern. Nothing in Step 7 writes to this table except an explicit
    PUT/PATCH the user makes."""

    __tablename__ = "user_job_search_goals"

    id: Mapped[int] = mapped_column(primary_key=True)

    target_roles: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    target_locations: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    remote_preference: Mapped[RemotePreference | None] = mapped_column(Enum(RemotePreference, name="remote_preference"))
    target_companies: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    minimum_match_score: Mapped[int | None] = mapped_column(Integer)
    applications_per_week: Mapped[int | None] = mapped_column(Integer)
    interviews_per_month: Mapped[int | None] = mapped_column(Integer)
    salary_min: Mapped[int | None] = mapped_column(Integer)
    salary_max: Mapped[int | None] = mapped_column(Integer)
    salary_currency: Mapped[str | None] = mapped_column(String(10))
    employment_types: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
