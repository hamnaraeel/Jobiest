"""Structured memory (spec sections 24-26, 67-68). Deliberately thin:
the agent's real "memory" is the existing Career Profile / Jobs /
Applications / Analytics / Recommendation tables (Steps 1-7) -- this
module only resolves conversational follow-ups ("prepare the top 3")
against a previous AgentTask's stored result, and produces a short
summary instead of dumping full JSON into an LLM prompt. It never stores
a second copy of profile or conversation data."""

from app.models.agent import AgentTask


def summarize_task_result(task: AgentTask | None, max_chars: int = 600) -> str | None:
    """A short, human-readable digest of what a previous task produced --
    used as LLM context for a follow-up request, not the raw JSON (spec
    section 68: don't send unrelated/oversized data to the LLM)."""

    if task is None or not task.final_result:
        return None

    result = task.final_result
    parts = [f"Objective: {task.objective or task.user_request}"]
    if "summary" in result:
        parts.append(str(result["summary"]))
    if "job_ids" in result:
        parts.append(f"Jobs found: {result['job_ids']}")
    if "application_ids" in result:
        parts.append(f"Applications: {result['application_ids']}")

    text = " | ".join(parts)
    return text[:max_chars]


def resolve_previous_job_ids(task: AgentTask | None, count: int | None) -> list[int]:
    """Resolves "the top N" / "those jobs" against a previous
    job_search(_and_prepare) task's ranked result. Returns [] (never a
    guess) if there's nothing to resolve against."""

    if task is None or not task.final_result:
        return []
    job_ids = task.final_result.get("ranked_job_ids") or task.final_result.get("job_ids") or []
    return job_ids[:count] if count else list(job_ids)


def resolve_previous_application_ids(task: AgentTask | None, count: int | None) -> list[int]:
    if task is None or not task.final_result:
        return []
    application_ids = task.final_result.get("application_ids") or []
    return application_ids[:count] if count else list(application_ids)
