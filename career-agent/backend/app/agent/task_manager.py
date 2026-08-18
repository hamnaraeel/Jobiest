"""DB access layer for AgentTask/AgentPlanStep/AgentEvent/AgentApproval
-- every read/write to those four tables goes through here, and this is
what turns rows into an AgentState snapshot (state.py) and back."""

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.agent.errors import TaskNotFoundError
from app.agent.state import AgentState, ApprovalView, PlanStepView
from app.models.agent import AgentApproval, AgentEvent, AgentPlanStep, AgentTask
from app.models.enums import AgentEventType, AgentPlanStepStatus, AgentTaskStatus


def create_task(db: Session, user_request: str, objective: str | None = None, context: dict | None = None) -> AgentTask:
    task = AgentTask(user_request=user_request, objective=objective, status=AgentTaskStatus.CREATED, context=context or {})
    db.add(task)
    db.commit()
    db.refresh(task)
    append_event(db, task.id, AgentEventType.TASK_CREATED, f"Task created: {user_request!r}")
    return task


def get_task(db: Session, task_id: int) -> AgentTask:
    task = db.get(AgentTask, task_id)
    if task is None:
        raise TaskNotFoundError(f"No agent task with id={task_id}.")
    return task


def list_tasks(db: Session, status: AgentTaskStatus | None = None, limit: int = 20, offset: int = 0) -> tuple[list[AgentTask], int]:
    stmt = select(AgentTask)
    count_stmt = select(func.count(AgentTask.id))
    if status:
        stmt = stmt.where(AgentTask.status == status)
        count_stmt = count_stmt.where(AgentTask.status == status)
    total = db.execute(count_stmt).scalar_one()
    items = db.execute(stmt.order_by(AgentTask.created_at.desc()).limit(limit).offset(offset)).scalars().all()
    return list(items), total


def update_task_status(db: Session, task: AgentTask, status: AgentTaskStatus, error_message: str | None = None) -> AgentTask:
    task.status = status
    if error_message is not None:
        task.error_message = error_message
    if status == AgentTaskStatus.RUNNING and task.started_at is None:
        task.started_at = datetime.now(timezone.utc)
    if status in (AgentTaskStatus.COMPLETED, AgentTaskStatus.FAILED, AgentTaskStatus.CANCELLED):
        task.completed_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(task)
    return task


def set_final_result(db: Session, task: AgentTask, result: dict) -> AgentTask:
    task.final_result = result
    db.commit()
    db.refresh(task)
    return task


def append_event(
    db: Session, task_id: int, event_type: AgentEventType, message: str,
    tool: str | None = None, metadata: dict | None = None, duration_ms: int | None = None,
) -> AgentEvent:
    event = AgentEvent(
        task_id=task_id, event_type=event_type, message=message, tool=tool,
        event_metadata=metadata or {}, duration_ms=duration_ms, timestamp=datetime.now(timezone.utc),
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


def list_events(db: Session, task_id: int) -> list[AgentEvent]:
    return list(db.execute(select(AgentEvent).where(AgentEvent.task_id == task_id).order_by(AgentEvent.timestamp)).scalars().all())


def create_plan_steps(db: Session, task_id: int, steps: list[dict]) -> list[AgentPlanStep]:
    """`steps` is a list of {action, tool, arguments, requires_approval}
    dicts, in execution order -- see planner.py."""

    rows = []
    for i, step in enumerate(steps, start=1):
        row = AgentPlanStep(
            task_id=task_id, step_number=i, action=step["action"], tool=step["tool"],
            arguments=step.get("arguments", {}), requires_approval=step.get("requires_approval", False),
            status=AgentPlanStepStatus.PENDING,
        )
        db.add(row)
        rows.append(row)
    db.commit()
    for row in rows:
        db.refresh(row)
    return rows


def list_steps(db: Session, task_id: int) -> list[AgentPlanStep]:
    return list(db.execute(select(AgentPlanStep).where(AgentPlanStep.task_id == task_id).order_by(AgentPlanStep.step_number)).scalars().all())


def update_step(
    db: Session, step: AgentPlanStep, status: AgentPlanStepStatus,
    result: dict | None = None, error_message: str | None = None,
) -> AgentPlanStep:
    step.status = status
    if result is not None:
        step.result = result
    if error_message is not None:
        step.error_message = error_message
    if status in (AgentPlanStepStatus.COMPLETED, AgentPlanStepStatus.FAILED, AgentPlanStepStatus.SKIPPED):
        step.completed_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(step)
    return step


def increment_retry(db: Session, step: AgentPlanStep) -> AgentPlanStep:
    step.retry_count += 1
    db.commit()
    db.refresh(step)
    return step


def list_approvals(db: Session, task_id: int, pending_only: bool = False) -> list[AgentApproval]:
    from app.models.enums import AgentApprovalStatus

    stmt = select(AgentApproval).where(AgentApproval.task_id == task_id)
    if pending_only:
        stmt = stmt.where(AgentApproval.status == AgentApprovalStatus.PENDING)
    return list(db.execute(stmt.order_by(AgentApproval.requested_at)).scalars().all())


def build_state(db: Session, task: AgentTask) -> AgentState:
    steps = list_steps(db, task.id)
    approvals = list_approvals(db, task.id)

    step_views = [
        PlanStepView(
            id=s.id, step_number=s.step_number, action=s.action, tool=s.tool, arguments=s.arguments,
            status=s.status.value, result=s.result, requires_approval=s.requires_approval, error_message=s.error_message,
        )
        for s in steps
    ]
    completed = [v for v in step_views if v.status in ("completed", "skipped")]
    pending = [v for v in step_views if v.status == "pending"]
    current_step = len(completed) + 1 if pending else len(step_views)

    approval_views = [
        ApprovalView(id=a.id, plan_step_id=a.plan_step_id, description=a.description, action_preview=a.action_preview, status=a.status.value)
        for a in approvals
    ]

    return AgentState(
        task_id=task.id, user_request=task.user_request, objective=task.objective, status=task.status,
        current_step=current_step, plan=step_views, completed_steps=completed, pending_steps=pending,
        approvals_required=[a for a in approval_views if a.status == "pending"],
        approvals_received=[a for a in approval_views if a.status != "pending"],
        errors=[v.error_message for v in step_views if v.error_message],
        final_result=task.final_result, created_at=task.created_at, updated_at=task.updated_at,
    )
