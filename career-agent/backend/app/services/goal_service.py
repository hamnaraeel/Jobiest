"""User-configured job-search goals (spec sections 35-36). Single-user
system, mirroring profile_service's pattern -- one current goal row,
never assumed or auto-populated, only ever set by an explicit user call."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.user_job_search_goal import UserJobSearchGoal
from app.services.analytics_service import overview


def get_current_goal(db: Session) -> UserJobSearchGoal | None:
    return db.execute(select(UserJobSearchGoal).order_by(UserJobSearchGoal.id.desc()).limit(1)).scalar_one_or_none()


def set_goal(db: Session, updates: dict) -> UserJobSearchGoal:
    """Creates the goal row if none exists yet, otherwise partially
    updates the current one (only the fields actually supplied)."""

    goal = get_current_goal(db)
    if goal is None:
        goal = UserJobSearchGoal()
        db.add(goal)
    for field, value in updates.items():
        if value is not None:
            setattr(goal, field, value)
    db.commit()
    db.refresh(goal)
    return goal


def _progress(actual: float, target: float | None) -> dict:
    if target is None or target <= 0:
        return {"goal": target, "actual": actual, "percent": None}
    return {"goal": target, "actual": actual, "percent": round(min(actual / target, 1.0) * 100)}


def goal_progress(db: Session, goal: UserJobSearchGoal) -> dict:
    """Compares actual recent activity against the configured goal --
    reports progress plainly, never framed as a shortfall/failure (spec
    section 36: "do not shame the user")."""

    metrics = overview(db)
    velocity = metrics["velocity"]
    interviews_this_month_estimate = velocity["interviews_per_month"]

    return {
        "applications_per_week": _progress(velocity["applications_per_week"], goal.applications_per_week),
        "interviews_per_month": _progress(interviews_this_month_estimate, goal.interviews_per_month),
    }
