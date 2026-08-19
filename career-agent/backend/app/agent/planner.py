"""Intent detection + plan generation (spec sections 15, 30).

Deterministic regex routing handles every example command in the spec
(sections 16-18, 47, 54-58, 77) without touching the LLM at all (spec
section 84: "do not use it for... simple CRUD, status lookup"). Only a
request that matches none of those patterns falls back to the local
Ollama model -- and even then, the LLM only *classifies* into one of the
same fixed intents and extracts a few known parameters; it never writes
a tool name or tool argument itself (see prompts.py's docstring). Once
the intent is known, the hand-written *_plan() functions below build the
actual AgentPlanStep list -- this is the deterministic planner spec
section 30 asks for.
"""

import re
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.agent import memory
from app.agent.errors import PlanningError
from app.agent.permissions import requires_approval
from app.agent.prompts import INTENT_SYSTEM_PROMPT, IntentClassification, IntentParameters, build_intent_user_prompt
from app.agent.tool_registry import get_tool
from app.agent.tools.jobs import DEFAULT_MIN_MATCH_SCORE
from app.ai.client import AIConfigurationError, OllamaResponseError, call_ollama_structured, get_ollama_client
from app.models.agent import AgentTask
from app.services import goal_service


def _min_match_score(db: Session) -> int:
    """The user's own configured minimum (Step 7 goal) if set, else the
    flowchart's default of 70 -- never invented, just respects what's
    already configured (or falls back sensibly if nothing is)."""

    goal = goal_service.get_current_goal(db)
    if goal and goal.minimum_match_score is not None:
        return goal.minimum_match_score
    return DEFAULT_MIN_MATCH_SCORE

# --- parameter extraction (used by both the deterministic and LLM paths) ---

_COUNT_RE = re.compile(r"\btop\s+(\d+)\b|\b(\d+)\b")
_REMOTE_RE = re.compile(r"\bremote\b", re.IGNORECASE)
_LOCATION_RE = re.compile(r"\bin\s+([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)*)")
_APPLICATION_ID_RE = re.compile(r"\bapplication\s*#?\s*(\d+)\b", re.IGNORECASE)
_JOB_ID_RE = re.compile(r"\bjob\s*#?\s*(\d+)\b", re.IGNORECASE)
_STRIP_RE = re.compile(
    r"^(find|search|show)\s+(me\s+)?(\d+\s+)?(good\s+|strong\s+|top\s+)*|"
    r"\s+jobs?\b.*$|\bin\s+[A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)*\b|\bremote\b|\band\b",
    re.IGNORECASE,
)


def _extract_parameters(message: str) -> IntentParameters:
    count_match = _COUNT_RE.search(message)
    count = int(next(g for g in (count_match.groups() if count_match else []) if g)) if count_match else None

    remote = bool(_REMOTE_RE.search(message))
    location_match = _LOCATION_RE.search(message)
    locations = [location_match.group(1)] + (["Remote"] if remote else []) if location_match else (["Remote"] if remote else [])

    role_text = _STRIP_RE.sub("", message).strip(" .,?!")
    keywords = [role_text] if role_text else []

    refers_to_previous = bool(re.search(r"\bthe top\b|\bthose\b|\bthem\b|\bthese\b", message, re.IGNORECASE)) and not keywords

    application_match = _APPLICATION_ID_RE.search(message)
    job_match = _JOB_ID_RE.search(message)

    return IntentParameters(
        count=count, keywords=keywords, locations=locations, refers_to_previous_result=refers_to_previous,
        application_id=int(application_match.group(1)) if application_match else None,
        job_id=int(job_match.group(1)) if job_match else None,
    )


_DETERMINISTIC_RULES: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\b(apply to|submit)\b.*\b(job|application)", re.IGNORECASE), "application_submission"),
    (re.compile(r"\bsubmit\b", re.IGNORECASE), "application_submission"),
    (re.compile(r"\bprepare\b.*\b(interview|for my interview)\b", re.IGNORECASE), "interview_preparation"),
    (re.compile(r"\binterview\b", re.IGNORECASE), "interview_preparation"),
    (re.compile(r"\bweekly\b.*\b(review|progress|goal)\b|\bhow am i doing\b", re.IGNORECASE), "weekly_review"),
    (re.compile(r"\bfollow.?up", re.IGNORECASE), "followup_management"),
    (re.compile(r"\bskill(s)?\b.*\b(learn|gap|need)\b|\bwhat skills\b", re.IGNORECASE), "skill_analysis"),
    (re.compile(r"\brejected\b|\brejection", re.IGNORECASE), "career_analysis"),
    (re.compile(r"\bfind\b.*\bjobs?\b.*\bprepare\b|\bprepare\b.*\bapplications?\b.*\bfor\b.*\bjobs?\b.*\bfind\b", re.IGNORECASE), "job_search_and_prepare"),
    (re.compile(r"\b(find|search)\b.{0,80}\bjobs?\b.*\band prepare\b", re.IGNORECASE), "job_search_and_prepare"),
    (re.compile(r"\bprepare\b.*\b(the top|top\s+\d+)\b|\bprepare\b.*\bapplications?\b", re.IGNORECASE), "application_preparation"),
    (re.compile(r"\breview\b.*\bapplications?\b|\bwhat needs attention\b|\bwhat should i apply to\b", re.IGNORECASE), "application_tracking"),
    (re.compile(r"\b(find|search)\b.*\bjobs?\b|\bshow\b.*\bjobs?\b", re.IGNORECASE), "job_search"),
    (re.compile(r"\bmy applications?\b|\bmy dashboard\b|\bmy status\b", re.IGNORECASE), "application_tracking"),
]


def detect_intent_deterministic(message: str) -> tuple[str, IntentParameters] | None:
    for pattern, intent in _DETERMINISTIC_RULES:
        if pattern.search(message):
            return intent, _extract_parameters(message)
    return None


def detect_intent_llm(message: str, previous_task: AgentTask | None) -> tuple[str, IntentParameters]:
    try:
        client = get_ollama_client()
    except AIConfigurationError as exc:
        raise PlanningError(
            f"This request wasn't recognized and the local LLM (Ollama) isn't configured to interpret it: {exc}"
        ) from exc

    summary = memory.summarize_task_result(previous_task)
    try:
        result = call_ollama_structured(
            client, INTENT_SYSTEM_PROMPT, build_intent_user_prompt(message, summary), IntentClassification,
        )
    except OllamaResponseError as exc:
        raise PlanningError(f"The local LLM could not classify this request: {exc}") from exc

    assert isinstance(result, IntentClassification)
    if result.intent == "unknown" or result.confidence < 0.4:
        raise PlanningError(
            f"This request is ambiguous (intent classification confidence {result.confidence:.2f}). "
            f"Try being more specific, e.g. 'Find 10 ML Engineer jobs' or 'Prepare the top 3 applications'."
        )
    return result.intent, result.parameters


@dataclass
class PlannedTask:
    intent: str
    objective: str
    steps: list[dict] = field(default_factory=list)


def _step(action: str, tool: str, arguments: dict | None = None) -> dict:
    spec = get_tool(tool)
    if spec is None:
        raise PlanningError(f"Planner referenced an unknown tool: '{tool}'.")
    declared = requires_approval(tool, spec.risk, spec.requires_approval)
    return {"action": action, "tool": tool, "arguments": arguments or {}, "requires_approval": declared}


# --- plan templates: one per intent, matching spec sections 16-18, 54-58 ---


def _plan_job_search(db: Session, params: IntentParameters) -> PlannedTask:
    """"Find jobs" means actually go find some, not just filter what's
    already stored -- discovery.run (Step 2b: Greenhouse/Lever/RemoteOK/
    WWR/Adzuna/USAJobs) runs first, using the same keywords/locations,
    so freshly-discovered jobs are in the database by the time
    jobs.search runs. discovery.run is itself dedup-aware, so running it
    on every search is safe -- it never creates duplicate Job rows."""

    discovery_args = {}
    if params.keywords:
        discovery_args["keywords"] = params.keywords
    if params.locations:
        discovery_args["locations"] = params.locations

    search_args = {"limit": params.count or 20}
    if params.keywords:
        search_args["role"] = params.keywords[0]
    if params.locations:
        search_args["location"] = params.locations[0]
    if "Remote" in params.locations:
        search_args["remote"] = True

    steps = [
        _step("discover_new_jobs", "discovery.run", discovery_args),
        _step("search_jobs", "jobs.search", search_args),
        _step("rank_jobs", "jobs.rank", {"job_ids": "$PREV_JOB_IDS", "top_n": params.count, "min_match_score": _min_match_score(db)}),
    ]
    return PlannedTask(intent="job_search", objective="Find and rank jobs matching the request.", steps=steps)


def _plan_job_search_and_prepare(db: Session, params: IntentParameters) -> PlannedTask:
    plan = _plan_job_search(db, params)
    plan.intent = "job_search_and_prepare"
    plan.objective = "Find strong-match jobs and prepare tailored applications for the best ones."
    plan.steps.append(_step("prepare_applications", "application.prepare_batch", {"job_ids": "$PREV_RANKED_JOB_IDS"}))
    return plan


def _plan_application_preparation(db: Session, params: IntentParameters, previous_task: AgentTask | None) -> PlannedTask:
    job_ids = [params.job_id] if params.job_id is not None else memory.resolve_previous_job_ids(previous_task, params.count)
    if not job_ids and not params.refers_to_previous_result:
        # No prior search to draw from -- rank whatever's currently shortlisted.
        steps = [
            _step("search_shortlisted_jobs", "jobs.search", {"status": "shortlisted", "limit": 50}),
            _step("rank_jobs", "jobs.rank", {"job_ids": "$PREV_JOB_IDS", "top_n": params.count or 5, "min_match_score": _min_match_score(db)}),
            _step("prepare_applications", "application.prepare_batch", {"job_ids": "$PREV_RANKED_JOB_IDS"}),
        ]
    else:
        steps = [_step("prepare_applications", "application.prepare_batch", {"job_ids": job_ids})]
    return PlannedTask(intent="application_preparation", objective="Prepare applications for the selected jobs.", steps=steps)


def _plan_application_submission(params: IntentParameters, previous_task: AgentTask | None) -> PlannedTask:
    """Per application: open the browser, detect CAPTCHA/login (the
    executor pauses cleanly and re-checks on resume if either is found --
    see executor._blocking_reason), fill known-safe fields (pausing the
    same way if anything needs an answer the agent must never guess),
    review, then submit -- the one HIGH-risk, always-approval-gated step.
    Mirrors spec section 18's own worked example exactly."""

    application_ids = [params.application_id] if params.application_id is not None else memory.resolve_previous_application_ids(previous_task, params.count)
    if not application_ids:
        raise PlanningError(
            "No specific applications were named and none were referenced from a previous task. "
            "Say which applications to submit, e.g. by id, or run 'prepare applications' first."
        )

    steps = []
    for aid in application_ids:
        args = {"application_id": aid}
        steps += [
            _step(f"start_browser_{aid}", "application.start", args),
            _step(f"analyze_page_{aid}", "application.analyze_page", args),
            _step(f"fill_application_{aid}", "application.fill", args),
            _step(f"review_application_{aid}", "application.review", args),
            _step(f"submit_application_{aid}", "application.submit", args),
        ]
    return PlannedTask(intent="application_submission", objective=f"Submit {len(application_ids)} application(s).", steps=steps)


def _plan_application_tracking() -> PlannedTask:
    steps = [
        _step("get_dashboard", "analytics.overview", {}),
        _step("search_applications", "applications.search", {"limit": 50}),
        _step("get_upcoming", "followups.upcoming", {}),
    ]
    return PlannedTask(intent="application_tracking", objective="Review current applications and what needs attention.", steps=steps)


def _plan_interview_preparation(params: IntentParameters, previous_task: AgentTask | None) -> PlannedTask:
    app_id = params.application_id
    if app_id is None:
        previous = memory.resolve_previous_application_ids(previous_task, 1)
        app_id = previous[0] if previous else None
    if app_id is not None:
        steps = [
            _step("get_interview_context", "interview.prepare", {"application_id": app_id}),
            _step("generate_questions", "interview.generate_questions", {"application_id": app_id}),
        ]
        return PlannedTask(intent="interview_preparation", objective="Prepare for the upcoming interview.", steps=steps)
    raise PlanningError("Which application's interview? Specify the application id (e.g. 'application 42'), or ask right after reviewing that application.")


def _plan_weekly_review() -> PlannedTask:
    steps = [
        _step("weekly_review", "analytics.weekly_review", {}),
        _step("career_strategy", "intelligence.strategy", {}),
    ]
    return PlannedTask(intent="weekly_review", objective="Summarize this week's progress and strategy.", steps=steps)


def _plan_followup_management() -> PlannedTask:
    steps = [_step("get_followups", "followups.upcoming", {})]
    return PlannedTask(intent="followup_management", objective="Show upcoming/overdue follow-ups.", steps=steps)


def _plan_skill_analysis() -> PlannedTask:
    steps = [_step("skill_gaps", "intelligence.skill_gaps", {})]
    return PlannedTask(intent="skill_analysis", objective="Identify skill gaps against currently analyzed jobs.", steps=steps)


def _plan_career_analysis() -> PlannedTask:
    steps = [_step("career_intelligence", "intelligence.career", {})]
    return PlannedTask(intent="career_analysis", objective="Review career-level performance and rejection patterns.", steps=steps)


def _resolve_job_ids(params: IntentParameters, previous_task: AgentTask | None, default_count: int | None) -> list[int]:
    if params.job_id is not None:
        return [params.job_id]
    return memory.resolve_previous_job_ids(previous_task, params.count or default_count)


def _plan_job_analysis(params: IntentParameters, previous_task: AgentTask | None) -> PlannedTask:
    job_ids = _resolve_job_ids(params, previous_task, None)
    if not job_ids:
        raise PlanningError("Which jobs? Specify job ids, or ask right after a job search.")
    steps = [_step(f"analyze_job_{jid}", "jobs.analyze", {"job_id": jid}) for jid in job_ids]
    steps += [_step(f"match_job_{jid}", "jobs.match", {"job_id": jid}) for jid in job_ids]
    return PlannedTask(intent="job_analysis", objective="Analyze and match the specified jobs.", steps=steps)


def _plan_job_shortlisting(params: IntentParameters, previous_task: AgentTask | None) -> PlannedTask:
    job_ids = memory.resolve_previous_job_ids(previous_task, None)
    if not job_ids:
        return PlannedTask(
            intent="job_shortlisting", objective="Rank shortlisted jobs.",
            steps=[
                _step("search_shortlisted", "jobs.search", {"status": "shortlisted", "limit": 50}),
                _step("rank_jobs", "jobs.rank", {"job_ids": "$PREV_JOB_IDS", "top_n": params.count}),
            ],
        )
    return PlannedTask(intent="job_shortlisting", objective="Rank the specified jobs.", steps=[_step("rank_jobs", "jobs.rank", {"job_ids": job_ids, "top_n": params.count})])


def _plan_cv_generation(params: IntentParameters, previous_task: AgentTask | None) -> PlannedTask:
    job_ids = _resolve_job_ids(params, previous_task, 1)
    if not job_ids:
        raise PlanningError("Which job should the CV be generated for? Specify a job id.")
    steps = [_step(f"generate_cv_{jid}", "cv.generate", {"job_id": jid}) for jid in job_ids]
    return PlannedTask(intent="cv_generation", objective="Generate tailored CV(s).", steps=steps)


def _plan_cover_letter_generation(params: IntentParameters, previous_task: AgentTask | None) -> PlannedTask:
    job_ids = _resolve_job_ids(params, previous_task, 1)
    if not job_ids:
        raise PlanningError("Which job should the cover letter be generated for? Specify a job id.")
    steps = [_step(f"generate_cover_letter_{jid}", "cover_letter.generate", {"job_id": jid}) for jid in job_ids]
    return PlannedTask(intent="cover_letter_generation", objective="Generate tailored cover letter(s).", steps=steps)


def build_plan(db: Session, intent: str, parameters: IntentParameters, previous_task: AgentTask | None) -> PlannedTask:
    if intent == "job_search":
        return _plan_job_search(db, parameters)
    if intent == "job_search_and_prepare":
        return _plan_job_search_and_prepare(db, parameters)
    if intent == "application_preparation":
        return _plan_application_preparation(db, parameters, previous_task)
    if intent == "application_submission":
        return _plan_application_submission(parameters, previous_task)
    if intent == "application_tracking":
        return _plan_application_tracking()
    if intent == "interview_preparation":
        return _plan_interview_preparation(parameters, previous_task)
    if intent == "weekly_review":
        return _plan_weekly_review()
    if intent == "followup_management":
        return _plan_followup_management()
    if intent == "skill_analysis":
        return _plan_skill_analysis()
    if intent == "career_analysis":
        return _plan_career_analysis()
    if intent == "job_analysis":
        return _plan_job_analysis(parameters, previous_task)
    if intent == "job_shortlisting":
        return _plan_job_shortlisting(parameters, previous_task)
    if intent == "cv_generation":
        return _plan_cv_generation(parameters, previous_task)
    if intent == "cover_letter_generation":
        return _plan_cover_letter_generation(parameters, previous_task)
    raise PlanningError(f"No plan template for intent '{intent}'.")


def plan_from_message(db: Session, message: str, previous_task: AgentTask | None) -> PlannedTask:
    detected = detect_intent_deterministic(message)
    if detected is None:
        detected = detect_intent_llm(message, previous_task)
    intent, parameters = detected
    return build_plan(db, intent, parameters, previous_task)
