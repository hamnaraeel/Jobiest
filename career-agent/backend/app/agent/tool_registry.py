"""The central tool registry (spec sections 7-10). Every capability the
agent can invoke is registered here exactly once, with a validated input
schema, a declared permission/risk level, and a handler that calls into
an existing Steps-1-7 service or API router function -- nothing here
reimplements that logic.

Tools are defined in app/agent/tools/*.py (one module per domain) and
register themselves via `register()` at import time; importing
app.agent.tools (below, at the bottom of this file) is what populates
REGISTRY. Nothing outside this package should construct a ToolSpec
directly.
"""

from dataclasses import dataclass, field
from typing import Awaitable, Callable

from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.models.enums import ToolPermission, ToolRiskLevel

ToolHandler = Callable[[Session, BaseModel], Awaitable[dict]]


@dataclass
class ToolSpec:
    name: str
    description: str
    input_schema: type[BaseModel]
    permission: ToolPermission
    risk: ToolRiskLevel
    handler: ToolHandler
    side_effects: list[str] = field(default_factory=list)
    requires_approval: bool = False

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema.model_json_schema(),
            "permission": self.permission.value,
            "risk": self.risk.value,
            "side_effects": self.side_effects,
            "requires_approval": self.requires_approval,
        }


REGISTRY: dict[str, ToolSpec] = {}


def register(spec: ToolSpec) -> None:
    if spec.name in REGISTRY:
        raise ValueError(f"Tool '{spec.name}' is already registered.")
    REGISTRY[spec.name] = spec


def get_tool(name: str) -> ToolSpec | None:
    return REGISTRY.get(name)


def list_tools() -> list[ToolSpec]:
    return sorted(REGISTRY.values(), key=lambda t: t.name)


# Populates REGISTRY as an import-time side effect -- see the module
# docstring above. Must stay at the bottom: the tools/* modules import
# ToolSpec/register/ToolHandler from this module, which must already be
# defined by the time they run.
from app.agent import tools as _tools  # noqa: F401,E402
