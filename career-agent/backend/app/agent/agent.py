"""Top-level orchestration entry point (spec section 65's POST
/agent/chat and the task-control endpoints call straight into this
module). Ties planner -> executor -> task_manager together; nothing
else should call executor.run_task directly."""

import logging

from sqlalchemy.orm import Session

from app.agent import executor, planner, task_manager, validators
from app.agent.errors import InvalidTaskStateError, PlanningError
from app.agent.tool_registry import REGISTRY
from app.models.agent import AgentTask
from app.models.enums import AgentEventType, AgentTaskStatus

logger = logging.getLogger("app.agent")

RESUMABLE_STATUSES = {AgentTaskStatus.PAUSED, AgentTaskStatus.WAITING_FOR_APPROVAL, AgentTaskStatus.WAITING_FOR_USER_INPUT}


async def handle_chat_message(db: Session, message: str, previous_task_id: int | None = None) -> AgentTask:
    """Creates a new AgentTask for `message`, plans it, and runs it until
    the first stop condition (spec section 74). previous_task_id lets a
    follow-up ("prepare the top 3") resolve against an earlier task's
    result (spec section 26) -- never implicit, always the caller's own
    explicit reference."""

    previous_task = task_manager.get_task(db, previous_task_id) if previous_task_id else None

    task = task_manager.create_task(db, user_request=message, context={"previous_task_id": previous_task_id} if previous_task_id else {})
    task_manager.update_task_status(db, task, AgentTaskStatus.PLANNING)
    task_manager.append_event(db, task.id, AgentEventType.PLANNING_STARTED, "Planning started.")

    # Tracked for GET /agent/usage (spec section 85) -- the deterministic
    # path never touches the LLM at all; only note it when it did.
    used_llm = planner.detect_intent_deterministic(message) is None

    try:
        planned = planner.plan_from_message(message, previous_task)
    except PlanningError as exc:
        task_manager.update_task_status(db, task, AgentTaskStatus.WAITING_FOR_USER_INPUT, error_message=str(exc))
        task_manager.append_event(db, task.id, AgentEventType.USER_INPUT_REQUIRED, str(exc), metadata={"used_llm": used_llm})
        task_manager.set_final_result(db, task, {
            "objective": None, "completed": [], "failed": [], "skipped": [], "pending_approvals": [],
            "warnings": [], "job_ids": [], "ranked_job_ids": [], "application_ids": [], "summary": str(exc),
        })
        return task

    task.objective = planned.objective
    db.commit()
    db.refresh(task)

    problems = validators.validate_plan_tools_exist(planned.steps, REGISTRY)
    if problems:
        task_manager.update_task_status(db, task, AgentTaskStatus.FAILED, error_message="; ".join(problems))
        task_manager.append_event(db, task.id, AgentEventType.TASK_FAILED, "; ".join(problems))
        return task

    task_manager.create_plan_steps(db, task.id, planned.steps)
    task_manager.append_event(
        db, task.id, AgentEventType.PLAN_CREATED, f"Plan created with {len(planned.steps)} step(s) for intent '{planned.intent}'.",
        metadata={"used_llm": used_llm, "intent": planned.intent},
    )

    return await executor.run_task(db, task)


async def resume_task(db: Session, task_id: int) -> AgentTask:
    task = task_manager.get_task(db, task_id)
    if task.status not in RESUMABLE_STATUSES:
        raise InvalidTaskStateError(f"Task {task_id} is '{task.status.value}' and cannot be resumed.")
    task_manager.append_event(db, task.id, AgentEventType.TASK_RESUMED, "Task resumed.")
    return await executor.run_task(db, task)


def pause_task(db: Session, task_id: int) -> AgentTask:
    task = task_manager.get_task(db, task_id)
    if task.status in (AgentTaskStatus.COMPLETED, AgentTaskStatus.FAILED, AgentTaskStatus.CANCELLED):
        raise InvalidTaskStateError(f"Task {task_id} is already '{task.status.value}' and cannot be paused.")
    task_manager.append_event(db, task.id, AgentEventType.TASK_PAUSED, "Task paused by user.")
    return task_manager.update_task_status(db, task, AgentTaskStatus.PAUSED)


async def cancel_task(db: Session, task_id: int) -> AgentTask:
    """Safely stops the task -- crucially, closes any browser session it
    opened (spec section 28) rather than leaving it running."""

    from app.api.browser_applications import cancel as cancel_application
    from app.models.enums import AgentPlanStepStatus

    task = task_manager.get_task(db, task_id)
    if task.status in (AgentTaskStatus.COMPLETED, AgentTaskStatus.CANCELLED):
        raise InvalidTaskStateError(f"Task {task_id} is already '{task.status.value}'.")

    for step in task_manager.list_steps(db, task_id):
        if step.tool == "application.start" and step.status == AgentPlanStepStatus.COMPLETED:
            application_id = step.arguments.get("application_id")
            if application_id:
                try:
                    await cancel_application(application_id=application_id, db=db)
                except Exception:  # noqa: BLE001 -- best-effort cleanup, must not block cancellation
                    logger.warning("failed to close browser session for application_id=%s during task cancel", application_id)

    task_manager.append_event(db, task.id, AgentEventType.TASK_CANCELLED, "Task cancelled by user.")
    return task_manager.update_task_status(db, task, AgentTaskStatus.CANCELLED)
