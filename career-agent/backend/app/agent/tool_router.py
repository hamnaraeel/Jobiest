"""The ONLY path from a plan step to an actual service call (spec
section 70) -- validates arguments against the tool's schema, invokes
its handler, and normalizes the result into the standard
{success, data, warnings, errors} shape (spec section 43).

Convention for handlers (app/agent/tools/*.py): return a plain dict of
domain data on success, or {"success": False, "errors": [...]} on a
handled failure (a 404, a validation error from the underlying service,
etc). Anything else raised is an unexpected error and propagates up to
the executor's own error handling."""

import logging
import time

from sqlalchemy.orm import Session

from app.agent.errors import ToolNotFoundError, ToolValidationError
from app.agent.tool_registry import get_tool

logger = logging.getLogger("app.agent.tool_router")


async def invoke(db: Session, tool_name: str, arguments: dict) -> tuple[dict, int]:
    """Returns (result_envelope, duration_ms)."""

    spec = get_tool(tool_name)
    if spec is None:
        raise ToolNotFoundError(f"Unknown tool: '{tool_name}'. Available tools: {sorted(t for t in _all_names())}")

    try:
        parsed_args = spec.input_schema.model_validate(arguments or {})
    except Exception as exc:  # pydantic ValidationError, kept generic on purpose
        raise ToolValidationError(f"Invalid arguments for tool '{tool_name}': {exc}") from exc

    started = time.monotonic()
    raw = await spec.handler(db, parsed_args)
    duration_ms = int((time.monotonic() - started) * 1000)

    if not isinstance(raw, dict):
        raw = {"result": raw}

    if raw.get("success") is False:
        envelope = {"success": False, "data": None, "warnings": raw.get("warnings", []), "errors": raw.get("errors") or ["Unknown error"]}
    else:
        warnings = raw.pop("warnings", []) if "warnings" in raw else []
        envelope = {"success": True, "data": raw, "warnings": warnings, "errors": []}

    return envelope, duration_ms


def _all_names():
    from app.agent.tool_registry import REGISTRY
    return REGISTRY.keys()
