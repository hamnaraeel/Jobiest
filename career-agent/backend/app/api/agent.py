import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.agent import agent as agent_module
from app.agent import approval_manager, task_manager
from app.agent.errors import ApprovalNotFoundError, InvalidTaskStateError, TaskNotFoundError
from app.db.database import get_db
from app.models.agent import AgentEvent
from app.models.enums import AgentTaskStatus
from app.schemas.agent import (
    ApprovalRead,
    ChatRequest,
    EventRead,
    PlanStepRead,
    TaskListResponse,
    TaskRead,
    UsageResponse,
)

logger = logging.getLogger("app.api.agent")

router = APIRouter(prefix="/agent", tags=["agent"])


@router.post("/chat", response_model=TaskRead, status_code=status.HTTP_201_CREATED)
async def chat(payload: ChatRequest, db: Session = Depends(get_db)):
    """Creates and runs a new agent task from a natural-language request,
    up to the first stop condition (plan complete, approval needed, user
    input needed, or MAX_AGENT_STEPS reached). Pass previous_task_id to
    resolve a follow-up like "prepare the top 3" against an earlier
    task's result."""

    return await agent_module.handle_chat_message(db, payload.message, payload.previous_task_id)


@router.get("/tasks", response_model=TaskListResponse)
def list_tasks(db: Session = Depends(get_db), status_filter: AgentTaskStatus | None = Query(None, alias="status"), limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0)):
    items, total = task_manager.list_tasks(db, status=status_filter, limit=limit, offset=offset)
    return TaskListResponse(items=items, total=total)


@router.get("/tasks/{task_id}", response_model=TaskRead)
def get_task(task_id: int, db: Session = Depends(get_db)):
    try:
        return task_manager.get_task(db, task_id)
    except TaskNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc))


@router.post("/tasks/{task_id}/pause", response_model=TaskRead)
def pause_task(task_id: int, db: Session = Depends(get_db)):
    try:
        return agent_module.pause_task(db, task_id)
    except TaskNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc))
    except InvalidTaskStateError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc))


@router.post("/tasks/{task_id}/resume", response_model=TaskRead)
async def resume_task(task_id: int, db: Session = Depends(get_db)):
    try:
        return await agent_module.resume_task(db, task_id)
    except TaskNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc))
    except InvalidTaskStateError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc))


@router.post("/tasks/{task_id}/cancel", response_model=TaskRead)
async def cancel_task(task_id: int, db: Session = Depends(get_db)):
    try:
        return await agent_module.cancel_task(db, task_id)
    except TaskNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc))
    except InvalidTaskStateError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc))


@router.get("/tasks/{task_id}/plan", response_model=list[PlanStepRead])
def get_task_plan(task_id: int, db: Session = Depends(get_db)):
    try:
        task_manager.get_task(db, task_id)
    except TaskNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc))
    return task_manager.list_steps(db, task_id)


@router.get("/tasks/{task_id}/events", response_model=list[EventRead])
def get_task_events(task_id: int, db: Session = Depends(get_db)):
    try:
        task_manager.get_task(db, task_id)
    except TaskNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc))
    return task_manager.list_events(db, task_id)


@router.get("/tasks/{task_id}/approvals", response_model=list[ApprovalRead])
def get_task_approvals(task_id: int, db: Session = Depends(get_db)):
    try:
        task_manager.get_task(db, task_id)
    except TaskNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc))
    approval_manager.expire_stale(db, task_id=task_id)
    return task_manager.list_approvals(db, task_id)


@router.post("/approvals/{approval_id}/approve", response_model=ApprovalRead)
async def approve(approval_id: int, db: Session = Depends(get_db)):
    """Approves the action, then immediately continues the task (spec
    section 13's own worked example: the agent picks back up right
    after approval, not only on a separate explicit /resume call)."""

    try:
        approval_row = approval_manager.get_approval(db, approval_id)
        approval_row = approval_manager.approve(db, approval_row)
    except ApprovalNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc))
    except InvalidTaskStateError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc))

    await agent_module.resume_task(db, approval_row.task_id)
    db.refresh(approval_row)
    return approval_row


@router.post("/approvals/{approval_id}/reject", response_model=ApprovalRead)
async def reject(approval_id: int, db: Session = Depends(get_db)):
    try:
        approval_row = approval_manager.get_approval(db, approval_id)
        approval_row = approval_manager.reject(db, approval_row)
    except ApprovalNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc))
    except InvalidTaskStateError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc))

    await agent_module.resume_task(db, approval_row.task_id)
    db.refresh(approval_row)
    return approval_row


@router.get("/usage", response_model=UsageResponse)
def get_usage(db: Session = Depends(get_db)):
    """Aggregated from the AgentEvent log (spec section 85) -- not a
    separate counters table, so it can never drift from what actually
    happened."""

    from app.models.agent import AgentTask
    from app.models.enums import AgentEventType

    total_tasks = db.execute(select(func.count(AgentTask.id))).scalar_one()

    tool_events = db.execute(select(AgentEvent).where(AgentEvent.event_type == AgentEventType.TOOL_COMPLETED)).scalars().all()
    tool_call_counts: dict[str, int] = {}
    total_execution_ms = 0
    browser_sessions_opened = 0
    for e in tool_events:
        if e.tool:
            tool_call_counts[e.tool] = tool_call_counts.get(e.tool, 0) + 1
            if e.tool == "application.start":
                browser_sessions_opened += 1
        total_execution_ms += e.duration_ms or 0

    plan_created_events = db.execute(select(AgentEvent).where(AgentEvent.event_type == AgentEventType.PLAN_CREATED)).scalars().all()
    total_llm_planning_calls = sum(1 for e in plan_created_events if e.event_metadata.get("used_llm"))

    return UsageResponse(
        total_tasks=total_tasks, total_tool_calls=len(tool_events), total_llm_planning_calls=total_llm_planning_calls,
        total_execution_ms=total_execution_ms, browser_sessions_opened=browser_sessions_opened, tool_call_counts=tool_call_counts,
    )
