"""Shared helper for tool handlers that call an existing FastAPI router
function directly (bypassing HTTP). Those functions raise HTTPException
on error paths -- fine when FastAPI catches it, but a tool handler needs
to turn it into the same {success, data, warnings, errors} shape every
other tool returns."""

from typing import Callable, TypeVar

from fastapi import HTTPException

T = TypeVar("T")


async def call_router(fn: Callable[..., T], *args, **kwargs) -> tuple[T | None, str | None]:
    """Calls a sync or async router function, returning (result, None)
    on success or (None, error_message) if it raised HTTPException."""

    try:
        result = fn(*args, **kwargs)
        if hasattr(result, "__await__"):
            result = await result
        return result, None
    except HTTPException as exc:
        return None, str(exc.detail)
