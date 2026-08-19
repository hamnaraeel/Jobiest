"""The controlled execution loop (spec section 3). Runs pending plan
steps in order, one at a time, until it hits a stop condition (spec
section 74): the plan finishes, a step needs approval, MAX_AGENT_STEPS
is reached, or an unrecoverable error occurs. Every stop is clean --
the task can always be resumed later from exactly where it left off,
since all state lives in the DB (AgentTask/AgentPlanStep/AgentApproval),
not in memory.
"""

import logging

from sqlalchemy.orm import Session

from app.agent import approval_manager, task_manager
from app.agent import tool_router
from app.agent.errors import InvalidTaskStateError, ToolNotFoundError, ToolValidationError
from app.config import get_settings
from app.models.agent import AgentPlanStep, AgentTask
from app.models.enums import AgentApprovalStatus, AgentEventType, AgentPlanStepStatus, AgentTaskStatus
from app.models.job import Job

logger = logging.getLogger("app.agent.executor")

# Never blindly retried, no matter what MAX_RETRIES says (spec section 37):
# an application submission or an external message must never be
# attempted twice just because the first attempt looked like it failed.
NEVER_RETRY_TOOLS = frozenset({"application.submit", "application.approve_submission"})


def _blocking_reason(tool: str, data: dict) -> str | None:
    """Some tools can succeed but still mean "a human needs to do
    something in the real world before this can continue" (spec sections
    14, 22-23: CAPTCHA, login, an unanswerable field) -- distinct from a
    tool failing. Returns a clear message describing what's needed, or
    None if the step can just proceed normally. The step that triggered
    this is left PENDING (not COMPLETED) so resuming re-runs it and
    naturally re-checks whether the blocker is now cleared."""

    if tool == "application.analyze_page":
        if data.get("captcha_detected"):
            indicator = data.get("captcha_indicator")
            return (
                f"A CAPTCHA was detected on the application page{f' ({indicator})' if indicator else ''}. "
                f"Complete it manually in the browser window, then resume this task."
            )
        if data.get("login_required"):
            return "This application requires logging in. Log in manually in the browser window, then resume this task."
        return None

    if tool == "application.fill":
        needs = data.get("needs_user_input") or []
        if needs:
            labels = ", ".join(f.get("label") or f.get("field_identifier") or f"field #{f.get('id')}" for f in needs)
            application_id = needs[0].get("application_id")
            return (
                f"{len(needs)} field(s) need your input before this application can continue: {labels}. "
                f"Answer each via POST /applications/{application_id}/fields/{{field_id}}/input "
                f"(salary/authorization/relocation-style questions are never guessed), then resume this task."
            )
        return None

    return None


# application.analyze_page's blocker (CAPTCHA/login) genuinely needs a
# fresh look at the live page, so it's left PENDING to retry itself.
# application.fill's blocker (a field needing an answer) is different --
# Step 5's fill() re-scans the whole page from scratch on every call, so
# re-running it doesn't recognize a field a human already answered via
# the separate provide_user_input endpoint the way GET .../review does.
# Its step is left COMPLETED; resuming moves on to review/submit instead
# of re-running fill.
RETRY_SAME_STEP_ON_BLOCK = frozenset({"application.analyze_page"})


def _resolve_placeholder(value, prior_result: dict | None):
    if not isinstance(value, str) or not value.startswith("$PREV_"):
        return value
    if prior_result is None:
        return value  # left as-is; the tool's own schema validation will report a clear error

    if value == "$PREV_JOB_IDS":
        if "job_ids" in prior_result:
            return prior_result["job_ids"]
        if "items" in prior_result:
            return [item["id"] for item in prior_result["items"]]
        return []
    if value == "$PREV_RANKED_JOB_IDS":
        return prior_result.get("ranked_job_ids", [])
    return value


def resolve_arguments(arguments: dict, prior_result: dict | None) -> dict:
    return {k: _resolve_placeholder(v, prior_result) for k, v in arguments.items()}


def _last_completed_result(db: Session, task_id: int) -> dict | None:
    steps = task_manager.list_steps(db, task_id)
    completed = [s for s in steps if s.status == AgentPlanStepStatus.COMPLETED]
    if not completed:
        return None
    result = completed[-1].result
    return (result or {}).get("data") if result else None


async def _execute_one_step(db: Session, task: AgentTask, step: AgentPlanStep, prior_result: dict | None) -> dict | None:
    """Runs exactly one step, updates its row, logs events. Returns the
    step's result envelope's `data` (for the next step's placeholder
    resolution) or None on failure."""

    resolved_args = resolve_arguments(step.arguments, prior_result)
    task_manager.append_event(db, task.id, AgentEventType.TOOL_STARTED, f"Step {step.step_number}: {step.action}", tool=step.tool, metadata={"arguments": _safe_metadata(resolved_args)})
    task_manager.update_step(db, step, AgentPlanStepStatus.RUNNING)

    try:
        envelope, duration_ms = await tool_router.invoke(db, step.tool, resolved_args)
    except (ToolNotFoundError, ToolValidationError) as exc:
        task_manager.update_step(db, step, AgentPlanStepStatus.FAILED, error_message=str(exc))
        task_manager.append_event(db, task.id, AgentEventType.TOOL_FAILED, str(exc), tool=step.tool)
        return None
    except Exception as exc:  # noqa: BLE001 -- one tool's bug must not crash the whole task
        logger.exception("tool '%s' raised an unexpected error", step.tool)
        task_manager.update_step(db, step, AgentPlanStepStatus.FAILED, error_message=f"Unexpected error: {exc}")
        task_manager.append_event(db, task.id, AgentEventType.TOOL_FAILED, f"Unexpected error: {exc}", tool=step.tool)
        return None

    if envelope["success"]:
        task_manager.update_step(db, step, AgentPlanStepStatus.COMPLETED, result=envelope)
        task_manager.append_event(
            db, task.id, AgentEventType.TOOL_COMPLETED, f"Step {step.step_number} completed: {step.action}",
            tool=step.tool, duration_ms=duration_ms, metadata={"warnings": envelope["warnings"]},
        )
        return envelope["data"]

    task_manager.update_step(db, step, AgentPlanStepStatus.FAILED, result=envelope, error_message="; ".join(envelope["errors"]))
    task_manager.append_event(db, task.id, AgentEventType.TOOL_FAILED, "; ".join(envelope["errors"]), tool=step.tool, duration_ms=duration_ms)
    return None


def _safe_metadata(arguments: dict) -> dict:
    """Never logs sensitive values verbatim (spec section 35) -- long
    free-text fields (cover-letter instructions, answers) are summarized
    by length instead of included."""

    safe = {}
    for k, v in arguments.items():
        if isinstance(v, str) and len(v) > 200:
            safe[k] = f"<{len(v)} chars>"
        else:
            safe[k] = v
    return safe


async def run_task(db: Session, task: AgentTask, max_steps: int | None = None) -> AgentTask:
    if task.status in (AgentTaskStatus.COMPLETED, AgentTaskStatus.CANCELLED):
        raise InvalidTaskStateError(f"Task {task.id} is already {task.status.value} and cannot be run further.")

    settings = get_settings()
    max_steps = max_steps or settings.max_agent_steps
    max_retries = settings.max_agent_retries

    approval_manager.expire_stale(db, task_id=task.id)
    task_manager.update_task_status(db, task, AgentTaskStatus.RUNNING)

    all_steps = task_manager.list_steps(db, task.id)
    prior_result = _last_completed_result(db, task.id)
    executed_this_call = 0

    for step in all_steps:
        if step.status not in (AgentPlanStepStatus.PENDING, AgentPlanStepStatus.WAITING_FOR_APPROVAL):
            if step.status == AgentPlanStepStatus.COMPLETED:
                continue
            if step.status == AgentPlanStepStatus.SKIPPED:
                continue
            if step.status == AgentPlanStepStatus.FAILED:
                # A failed step stops the task; resuming a failed task isn't supported --
                # start a new one. (Distinct from WAITING_FOR_APPROVAL/PAUSED, which are.)
                break
            continue

        if executed_this_call >= max_steps:
            task_manager.update_task_status(db, task, AgentTaskStatus.PAUSED)
            task_manager.append_event(
                db, task.id, AgentEventType.TASK_PAUSED,
                f"Reached the maximum of {max_steps} agent steps for this run; task paused, not failed -- resume to continue.",
            )
            return task

        if step.requires_approval:
            approvals = [a for a in task_manager.list_approvals(db, task.id) if a.plan_step_id == step.id]
            approval = approvals[-1] if approvals else None

            if approval is None:
                preview = _action_preview(db, step)
                approval_manager.request_approval(
                    db, task.id, description=f"Approve: {step.action} ({step.tool})",
                    action_preview=preview, plan_step_id=step.id,
                )
                task_manager.update_step(db, step, AgentPlanStepStatus.WAITING_FOR_APPROVAL)
                task_manager.update_task_status(db, task, AgentTaskStatus.WAITING_FOR_APPROVAL)
                task_manager.append_event(
                    db, task.id, AgentEventType.APPROVAL_REQUESTED,
                    f"Step {step.step_number} ({step.action}) needs approval before it can run.", tool=step.tool,
                )
                return task
            if approval.status == AgentApprovalStatus.PENDING:
                task_manager.update_task_status(db, task, AgentTaskStatus.WAITING_FOR_APPROVAL)
                return task
            if approval.status == AgentApprovalStatus.REJECTED:
                task_manager.update_step(db, step, AgentPlanStepStatus.SKIPPED, error_message="Rejected by user.")
                task_manager.append_event(db, task.id, AgentEventType.APPROVAL_RECEIVED, f"Step {step.step_number} rejected -- skipped.", tool=step.tool)
                executed_this_call += 1
                continue
            if approval.status == AgentApprovalStatus.EXPIRED:
                task_manager.update_step(db, step, AgentPlanStepStatus.SKIPPED, error_message="Approval expired without a decision.")
                executed_this_call += 1
                continue
            # APPROVED -> fall through and execute.
            task_manager.append_event(db, task.id, AgentEventType.APPROVAL_RECEIVED, f"Step {step.step_number} approved -- proceeding.", tool=step.tool)

        result_data = await _execute_one_step(db, task, step, prior_result)
        executed_this_call += 1

        if result_data is not None:
            blocking_message = _blocking_reason(step.tool, result_data)
            if blocking_message:
                db.refresh(step)
                if step.tool in RETRY_SAME_STEP_ON_BLOCK:
                    task_manager.update_step(db, step, AgentPlanStepStatus.PENDING)
                task_manager.update_task_status(db, task, AgentTaskStatus.WAITING_FOR_USER_INPUT)
                task_manager.append_event(db, task.id, AgentEventType.USER_INPUT_REQUIRED, blocking_message, tool=step.tool)
                return task

        if result_data is None:
            db.refresh(step)
            if step.tool not in NEVER_RETRY_TOOLS and step.retry_count < max_retries:
                task_manager.increment_retry(db, step)
                task_manager.update_step(db, step, AgentPlanStepStatus.PENDING)
                task_manager.append_event(
                    db, task.id, AgentEventType.TOOL_STARTED,
                    f"Retrying step {step.step_number} (attempt {step.retry_count + 1}/{max_retries + 1}).", tool=step.tool,
                )
                result_data = await _execute_one_step(db, task, step, prior_result)
                executed_this_call += 1

        if result_data is None:
            task_manager.update_task_status(db, task, AgentTaskStatus.FAILED, error_message=f"Step {step.step_number} ({step.action}) failed: {step.error_message}")
            task_manager.append_event(db, task.id, AgentEventType.TASK_FAILED, f"Task failed at step {step.step_number}: {step.error_message}")
            return task

        prior_result = result_data

    task_manager.update_task_status(db, task, AgentTaskStatus.COMPLETED)
    final_result = _build_final_result(db, task)
    task_manager.set_final_result(db, task, final_result)
    task_manager.append_event(db, task.id, AgentEventType.TASK_COMPLETED, "Task completed.")
    return task


def _action_preview(db: Session, step: AgentPlanStep) -> dict:
    """Human-readable preview shown before a HIGH-impact action (spec
    section 46) -- resolves a job/application id in the step's arguments
    into a short label where possible, rather than a bare integer."""

    preview = {"tool": step.tool, "arguments": step.arguments}
    application_id = step.arguments.get("application_id")
    if application_id:
        from app.models.application import Application
        application = db.get(Application, application_id)
        if application:
            job = db.get(Job, application.job_id)
            preview["target"] = f"{job.title if job else '?'} at {job.company if job else '?'} (application #{application_id})"
    return preview


def _build_final_result(db: Session, task: AgentTask) -> dict:
    """The structured summary (spec sections 44, 86) -- OBJECTIVE /
    COMPLETED / RESULT / PENDING / APPROVAL REQUIRED / WARNINGS."""

    steps = task_manager.list_steps(db, task.id)
    approvals = task_manager.list_approvals(db, task.id)

    completed = [s for s in steps if s.status == AgentPlanStepStatus.COMPLETED]
    failed = [s for s in steps if s.status == AgentPlanStepStatus.FAILED]
    skipped = [s for s in steps if s.status == AgentPlanStepStatus.SKIPPED]
    pending_approvals = [a for a in approvals if a.status == AgentApprovalStatus.PENDING]

    job_ids, ranked_job_ids, application_ids = [], [], []
    for s in completed:
        data = (s.result or {}).get("data") or {}
        if "job_ids" in data:
            job_ids = data["job_ids"]
        if "items" in data and all(isinstance(i, dict) and "id" in i for i in data["items"]):
            job_ids = [i["id"] for i in data["items"]]
        if "ranked_job_ids" in data:
            ranked_job_ids = data["ranked_job_ids"]
        if "application_ids" in data:
            application_ids = data["application_ids"]
        if "application_id" in data:
            application_ids.append(data["application_id"])

    warnings = []
    for s in completed:
        warnings.extend((s.result or {}).get("warnings", []))

    return {
        "objective": task.objective,
        "completed": [f"{s.action}" for s in completed],
        "failed": [f"{s.action}: {s.error_message}" for s in failed],
        "skipped": [f"{s.action}: {s.error_message}" for s in skipped],
        "pending_approvals": [a.description for a in pending_approvals],
        "warnings": warnings,
        "job_ids": job_ids,
        "ranked_job_ids": ranked_job_ids,
        "application_ids": application_ids,
        "summary": _text_summary(task, completed, failed, skipped, pending_approvals, warnings),
    }


def _text_summary(task, completed, failed, skipped, pending_approvals, warnings) -> str:
    lines = [f"OBJECTIVE: {task.objective or task.user_request}", "", "COMPLETED:"]
    lines += [f"  ✓ {s.action}" for s in completed] or ["  (none)"]
    if failed:
        lines += ["", "FAILED:"] + [f"  ✗ {s.action}: {s.error_message}" for s in failed]
    if skipped:
        lines += ["", "SKIPPED:"] + [f"  - {s.action}: {s.error_message}" for s in skipped]
    lines += ["", "APPROVAL REQUIRED:"]
    lines += [f"  - {a.description}" for a in pending_approvals] or ["  (none)"]
    if warnings:
        lines += ["", "WARNINGS:"] + [f"  ! {w}" for w in warnings]
    return "\n".join(lines)
