from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.enums import AgentApprovalStatus, AgentEventType, AgentPlanStepStatus, AgentTaskStatus, PriorityLevel


class ChatRequest(BaseModel):
    message: str
    previous_task_id: int | None = None


class PlanStepRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    step_number: int
    action: str
    tool: str
    arguments: dict
    status: AgentPlanStepStatus
    result: dict | None
    requires_approval: bool
    error_message: str | None
    retry_count: int
    completed_at: datetime | None


class TaskRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_request: str
    objective: str | None
    status: AgentTaskStatus
    priority: PriorityLevel
    context: dict
    final_result: dict | None
    started_at: datetime | None
    completed_at: datetime | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime


class TaskListResponse(BaseModel):
    items: list[TaskRead]
    total: int


class EventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    event_type: AgentEventType
    message: str
    tool: str | None
    duration_ms: int | None
    event_metadata: dict
    timestamp: datetime


class ApprovalRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    task_id: int
    plan_step_id: int | None
    description: str
    action_preview: dict
    status: AgentApprovalStatus
    requested_at: datetime
    decided_at: datetime | None
    expires_at: datetime | None


class UsageResponse(BaseModel):
    total_tasks: int
    total_tool_calls: int
    total_llm_planning_calls: int
    total_execution_ms: int
    browser_sessions_opened: int
    tool_call_counts: dict[str, int]
