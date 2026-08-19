"""The approval policy (spec sections 9-11, 50). This is the one place
that decides whether a tool call may run automatically or must stop and
wait for an explicit human decision -- never inferred from conversational
text (spec section 13), never bypassable by an LLM (spec section 70).

Policy:
  LOW    -> always runs automatically.
  MEDIUM -> runs automatically UNLESS the tool is in ALWAYS_REQUIRES_APPROVAL
            (i.e. it touches "important persistent data").
  HIGH   -> always requires approval, no exceptions.
"""

from app.models.enums import ToolRiskLevel

# Tools that touch important persistent data or leave this machine --
# always gated regardless of their nominal risk level (spec section 11's
# examples: application submission, recruiter/external messages, Career
# Profile changes, job-search preference changes, offer acceptance).
ALWAYS_REQUIRES_APPROVAL: frozenset[str] = frozenset({
    "application.approve_submission",
    "application.submit",
    "career.update_profile",
    "career.update_goals",
    "career.confirm_resume_import",
    "application.accept_offer",
    "message.send",
})


def requires_approval(tool_name: str, risk: ToolRiskLevel, declared: bool) -> bool:
    """A tool's ToolSpec.requires_approval is the floor, not the
    ceiling -- this can only turn a `False` into `True`, matching a
    stricter global rule; it never weakens an explicitly-declared
    approval requirement."""

    if declared:
        return True
    if tool_name in ALWAYS_REQUIRES_APPROVAL:
        return True
    if risk == ToolRiskLevel.HIGH:
        return True
    return False
