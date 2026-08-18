"""Step 8: AI job search agent / orchestrator -- persistence for tasks,
their plans, their execution log, and approvals. The agent's own
"memory" is deliberately thin: it never duplicates the Career Profile or
any Steps-1-7 data (spec section 24) -- these four tables only track
*orchestration* state (what was asked, what plan was made, what happened,
what needs a decision). See app/agent/memory.py for how real context is
retrieved from the existing Steps-1-7 tables instead of copied here.
"""

from datetime import datetime

from sqlalchemy import JSON, DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import (
    AgentApprovalStatus,
    AgentEventType,
    AgentPlanStepStatus,
    AgentTaskStatus,
    PriorityLevel,
)
from app.models.mixins import TimestampMixin


class AgentTask(Base, TimestampMixin):
    """One user-level agent request (spec section 5). Everything the
    agent does traces back to exactly one of these."""

    __tablename__ = "agent_tasks"

    id: Mapped[int] = mapped_column(primary_key=True)

    user_request: Mapped[str] = mapped_column(Text, nullable=False)
    objective: Mapped[str | None] = mapped_column(Text)
    status: Mapped[AgentTaskStatus] = mapped_column(
        Enum(AgentTaskStatus, name="agent_task_status"), default=AgentTaskStatus.CREATED, nullable=False, index=True
    )
    priority: Mapped[PriorityLevel] = mapped_column(Enum(PriorityLevel, name="priority_level"), default=PriorityLevel.MEDIUM, nullable=False)

    # Conversational continuity (spec section 26): the ids/results a
    # follow-up request like "prepare the top 3" resolves against. Not a
    # second Career Profile -- just "what did the last task in this
    # thread produce," small and structured.
    context: Mapped[dict] = mapped_column(JSON, default=dict)
    final_result: Mapped[dict | None] = mapped_column(JSON)

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_message: Mapped[str | None] = mapped_column(Text)

    steps: Mapped[list["AgentPlanStep"]] = relationship(back_populates="task", cascade="all, delete-orphan", order_by="AgentPlanStep.step_number")
    events: Mapped[list["AgentEvent"]] = relationship(back_populates="task", cascade="all, delete-orphan", order_by="AgentEvent.timestamp")
    approvals: Mapped[list["AgentApproval"]] = relationship(back_populates="task", cascade="all, delete-orphan")


class AgentPlanStep(Base, TimestampMixin):
    """One step of an AgentTask's plan (spec section 6 -- "AgentPlan").
    Named *PlanStep* here since each row is a single ordered step, not
    the whole plan; the ordered collection of a task's steps *is* the
    plan."""

    __tablename__ = "agent_plan_steps"

    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("agent_tasks.id", ondelete="CASCADE"), nullable=False, index=True)

    step_number: Mapped[int] = mapped_column(Integer, nullable=False)
    action: Mapped[str] = mapped_column(String(255), nullable=False)
    tool: Mapped[str] = mapped_column(String(255), nullable=False)
    arguments: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[AgentPlanStepStatus] = mapped_column(
        Enum(AgentPlanStepStatus, name="agent_plan_step_status"), default=AgentPlanStepStatus.PENDING, nullable=False
    )
    result: Mapped[dict | None] = mapped_column(JSON)
    requires_approval: Mapped[bool] = mapped_column(default=False, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text)
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    task: Mapped["AgentTask"] = relationship(back_populates="steps")


class AgentEvent(Base):
    """Append-only execution log (spec section 66) -- the same pattern
    as Step 5's ApplicationEvent, one row per thing the agent did or
    decided, in order. This is also what GET /agent/usage aggregates
    over rather than a separate counters table (spec section 85)."""

    __tablename__ = "agent_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("agent_tasks.id", ondelete="CASCADE"), nullable=False, index=True)

    event_type: Mapped[AgentEventType] = mapped_column(Enum(AgentEventType, name="agent_event_type"), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    tool: Mapped[str | None] = mapped_column(String(255))
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    event_metadata: Mapped[dict] = mapped_column(JSON, default=dict)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)

    task: Mapped["AgentTask"] = relationship(back_populates="events")


class AgentApproval(Base, TimestampMixin):
    """One thing waiting on an explicit human decision (spec sections
    12-13, 19-20). Never inferred from conversational text -- only
    POST /agent/approvals/{id}/approve|reject changes .status."""

    __tablename__ = "agent_approvals"

    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("agent_tasks.id", ondelete="CASCADE"), nullable=False, index=True)
    plan_step_id: Mapped[int | None] = mapped_column(ForeignKey("agent_plan_steps.id", ondelete="CASCADE"))

    description: Mapped[str] = mapped_column(Text, nullable=False)
    action_preview: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[AgentApprovalStatus] = mapped_column(
        Enum(AgentApprovalStatus, name="agent_approval_status"), default=AgentApprovalStatus.PENDING, nullable=False, index=True
    )
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    task: Mapped["AgentTask"] = relationship(back_populates="approvals")
    plan_step: Mapped["AgentPlanStep | None"] = relationship()
