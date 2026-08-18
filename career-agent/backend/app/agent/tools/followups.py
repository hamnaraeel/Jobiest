"""Step 6 follow-up wrappers. Read-only by design (spec section 58: "Do
not send messages automatically") -- there is deliberately no
followups.send tool; sending anything external is out of scope until a
real connector exists (see spec section 51, not implemented)."""

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.agent.tool_registry import ToolSpec, register
from app.api.tracking import get_upcoming_calendar, get_upcoming_notifications
from app.models.enums import ToolPermission, ToolRiskLevel
from app.schemas.tracking import CalendarItem, NotificationItem


class UpcomingArgs(BaseModel):
    within_days: int = Field(14, ge=1, le=90)


class CalendarArgs(BaseModel):
    within_days: int = Field(30, ge=1, le=180)


async def followups_upcoming(db: Session, args: UpcomingArgs) -> dict:
    # Both of these service calls return list[dict] -- FastAPI's
    # response_model normally validates each into NotificationItem/
    # CalendarItem at the HTTP layer; done explicitly here instead.
    items = get_upcoming_notifications(within_days=args.within_days, db=db)
    return {"items": [NotificationItem.model_validate(item).model_dump(mode="json") for item in items]}


async def followups_calendar(db: Session, args: CalendarArgs) -> dict:
    items = get_upcoming_calendar(within_days=args.within_days, db=db)
    return {"items": [CalendarItem.model_validate(item).model_dump(mode="json") for item in items]}


register(ToolSpec(
    name="followups.upcoming", description="Upcoming/overdue follow-ups, interviews, and deadlines needing attention.",
    input_schema=UpcomingArgs, permission=ToolPermission.READ_ONLY, risk=ToolRiskLevel.LOW, handler=followups_upcoming,
))
register(ToolSpec(
    name="followups.calendar", description="Upcoming calendar items (interviews, follow-ups, deadlines) over a wider window.",
    input_schema=CalendarArgs, permission=ToolPermission.READ_ONLY, risk=ToolRiskLevel.LOW, handler=followups_calendar,
))
