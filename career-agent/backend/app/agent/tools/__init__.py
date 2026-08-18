"""Importing this package registers every tool as a side effect --
tool_registry.py imports this module once, at the bottom of its own
file, to populate REGISTRY. Add a new domain module here to expose it."""

from app.agent.tools import (  # noqa: F401
    analytics,
    application,
    career,
    cover_letter,
    cv,
    discovery,
    followups,
    intelligence,
    interview,
    jobs,
)
