"""The approval lifecycle (spec section 12). This is the ONLY place an
AgentApproval's status changes -- nothing infers approval from
conversational text ("okay", "looks good"); only approve()/reject(),
called from POST /agent/approvals/{id}/approve|reject, ever does."""

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent.errors import ApprovalNotFoundError, InvalidTaskStateError
from app.models.agent import AgentApproval
from app.models.enums import AgentApprovalStatus

DEFAULT_EXPIRY_HOURS = 72


def request_approval(
    db: Session, task_id: int, description: str, action_preview: dict,
    plan_step_id: int | None = None, expires_in_hours: int | None = DEFAULT_EXPIRY_HOURS,
) -> AgentApproval:
    now = datetime.now(timezone.utc)
    approval = AgentApproval(
        task_id=task_id, plan_step_id=plan_step_id, description=description, action_preview=action_preview,
        status=AgentApprovalStatus.PENDING, requested_at=now,
        expires_at=(now + timedelta(hours=expires_in_hours)) if expires_in_hours else None,
    )
    db.add(approval)
    db.commit()
    db.refresh(approval)
    return approval


def get_approval(db: Session, approval_id: int) -> AgentApproval:
    approval = db.get(AgentApproval, approval_id)
    if approval is None:
        raise ApprovalNotFoundError(f"No approval with id={approval_id}.")
    return approval


def _require_pending(approval: AgentApproval) -> None:
    if approval.status != AgentApprovalStatus.PENDING:
        raise InvalidTaskStateError(f"Approval {approval.id} is already '{approval.status.value}', not pending.")


def approve(db: Session, approval: AgentApproval) -> AgentApproval:
    _require_pending(approval)
    approval.status = AgentApprovalStatus.APPROVED
    approval.decided_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(approval)
    return approval


def reject(db: Session, approval: AgentApproval) -> AgentApproval:
    _require_pending(approval)
    approval.status = AgentApprovalStatus.REJECTED
    approval.decided_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(approval)
    return approval


def is_approved(approval: AgentApproval) -> bool:
    return approval.status == AgentApprovalStatus.APPROVED


def expire(db: Session, approval: AgentApproval) -> AgentApproval:
    approval.status = AgentApprovalStatus.EXPIRED
    approval.decided_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(approval)
    return approval


def expire_stale(db: Session, task_id: int | None = None) -> list[AgentApproval]:
    """Opportunistically expires pending approvals past their
    expires_at. Called before reading approval state so a stale approval
    is never silently actioned on."""

    stmt = select(AgentApproval).where(
        AgentApproval.status == AgentApprovalStatus.PENDING,
        AgentApproval.expires_at.is_not(None),
        AgentApproval.expires_at < datetime.now(timezone.utc),
    )
    if task_id is not None:
        stmt = stmt.where(AgentApproval.task_id == task_id)

    stale = list(db.execute(stmt).scalars().all())
    return [expire(db, a) for a in stale]
