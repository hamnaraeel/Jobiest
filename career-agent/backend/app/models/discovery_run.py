from datetime import datetime

from sqlalchemy import ARRAY, JSON, DateTime, Enum, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.enums import DiscoveryTrigger
from app.models.mixins import TimestampMixin


class DiscoveryRun(Base, TimestampMixin):
    """One invocation of Step 8's job discovery (manual or scheduled).
    Append-only log, like ApplicationEvent -- lets the user see exactly
    what was searched, which sources succeeded/failed, and how many jobs
    each one found/created, without re-running anything."""

    __tablename__ = "discovery_runs"

    id: Mapped[int] = mapped_column(primary_key=True)

    trigger: Mapped[DiscoveryTrigger] = mapped_column(Enum(DiscoveryTrigger, name="discovery_trigger"), nullable=False)
    sources: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    query: Mapped[dict] = mapped_column(JSON, default=dict)
    # Per-source breakdown: {"greenhouse": {"found": 3, "created": 2, "duplicate": 1, "error": null}, ...}
    results: Mapped[dict] = mapped_column(JSON, default=dict)
    jobs_found: Mapped[int] = mapped_column(Integer, default=0)
    jobs_created: Mapped[int] = mapped_column(Integer, default=0)

    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
