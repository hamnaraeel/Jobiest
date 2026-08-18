"""Agent-specific exception hierarchy. API routers turn these into clear
4xx responses (see app/api/agent.py) rather than opaque 500s -- the same
pattern Steps 2-7 use for their own domain errors."""


class AgentError(Exception):
    """Base class for every agent-layer error."""


class PlanningError(AgentError):
    """The planner could not turn the request into a valid plan."""


class ToolNotFoundError(AgentError):
    """The plan (or a user/LLM-suggested action) named a tool that isn't
    in the registry. The agent can only ever call registered tools --
    this is what makes "the LLM can't execute arbitrary code" true."""


class ToolValidationError(AgentError):
    """A tool's arguments failed schema or dependency validation before
    execution (spec section 31) -- e.g. cv.generate for a job_id that
    doesn't exist, or application.submit for an unapproved application."""


class PermissionDeniedError(AgentError):
    """A tool call was blocked by the permission/risk policy (should be
    rare -- most blocking happens earlier, via requires_approval)."""


class ApprovalRequiredError(AgentError):
    """Raised internally when the executor reaches a step that needs a
    decision it doesn't have yet. Not a failure -- the task moves to
    WAITING_FOR_APPROVAL and stops cleanly; see executor.py."""


class UserInputRequiredError(AgentError):
    """Raised internally when a step needs information the system
    doesn't have and must not guess (spec section 14)."""


class MaxStepsExceededError(AgentError):
    """MAX_AGENT_STEPS was reached (spec section 75). The task pauses,
    it does not fail -- it can still be resumed."""


class TaskNotFoundError(AgentError):
    pass


class ApprovalNotFoundError(AgentError):
    pass


class InvalidTaskStateError(AgentError):
    """E.g. trying to resume a task that's already completed."""
