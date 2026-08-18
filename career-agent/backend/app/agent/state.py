"""AgentState (spec section 4) -- a lightweight, in-memory snapshot of a
task's current situation, assembled from the AgentTask/AgentPlanStep/
AgentEvent/AgentApproval rows (the actual source of truth). The planner
and executor read/act on this snapshot rather than poking at ORM rows
directly; task_manager.py is what turns DB rows into one of these and
back."""

from dataclasses import dataclass, field
from datetime import datetime

from app.models.enums import AgentTaskStatus


@dataclass
class PlanStepView:
    id: int
    step_number: int
    action: str
    tool: str
    arguments: dict
    status: str
    result: dict | None
    requires_approval: bool
    error_message: str | None = None


@dataclass
class ApprovalView:
    id: int
    plan_step_id: int | None
    description: str
    action_preview: dict
    status: str


@dataclass
class AgentState:
    task_id: int
    user_request: str
    objective: str | None
    status: AgentTaskStatus
    current_step: int
    plan: list[PlanStepView] = field(default_factory=list)
    completed_steps: list[PlanStepView] = field(default_factory=list)
    pending_steps: list[PlanStepView] = field(default_factory=list)
    tool_calls: list[dict] = field(default_factory=list)
    approvals_required: list[ApprovalView] = field(default_factory=list)
    approvals_received: list[ApprovalView] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    final_result: dict | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def next_pending_step(self) -> PlanStepView | None:
        return self.pending_steps[0] if self.pending_steps else None
