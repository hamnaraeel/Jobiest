from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg2://postgres:postgres@localhost:5432/career_agent"
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"

    # Free alternative to OpenAI for Steps 2-3/1b (JD analysis, matching, CV
    # customization, resume parsing): Groq hosts full-size open models on
    # its own GPUs behind an OpenAI-compatible endpoint, so the same
    # `.chat.completions.parse()` structured-output calls work unmodified
    # -- just point the client at Groq's base_url. Set AI_PROVIDER=groq to
    # use it in place of OpenAI for those four services.
    ai_provider: str = "openai"
    groq_api_key: str = ""
    # gpt-oss-20b, not the larger 120b: same free-tier 8000 tokens/minute
    # cap applies to both, and 20b's lighter reasoning overhead leaves far
    # more of that budget for the actual JSON response (see
    # STRUCTURED_OUTPUT_MAX_TOKENS in ai/client.py).
    groq_model: str = "openai/gpt-oss-20b"
    groq_base_url: str = "https://api.groq.com/openai/v1"

    # A real CV now always includes the full Career Profile verbatim (no
    # AI trimming of experiences/projects/bullets -- see
    # cv_customization_service.py), so a 1-page target is unrealistic for
    # most candidates. 2 pages (+1 page tolerance below, so up to 3
    # actually warns) is a more realistic default; still warning-only,
    # never a hard block on generation.
    cv_max_pages: int = 2
    cv_storage_dir: str = "../data/cvs"
    pdflatex_path: str = "pdflatex"

    # Step 4: local-only LLM (Ollama) for cover letters / application
    # answers. Never a paid API -- see AIConfigurationError in ai/client.py
    # for what happens if OLLAMA_MODEL is left unset.
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = ""

    cover_letter_min_words: int = 250
    cover_letter_max_words: int = 400
    application_materials_dir: str = "../data/application_materials"

    # Step 5: browser-based application assistant. DRY_RUN defaults True
    # on purpose -- the agent never clicks a real submit button unless
    # this is explicitly set to false AND the user has separately called
    # POST /applications/{id}/approve-submission. Headless defaults False
    # so you can watch the browser during development.
    dry_run: bool = True
    browser_headless: bool = False
    browser_type: str = "chromium"
    browser_profile_dir: str = "../data/browser_profile"
    browser_screenshots: bool = False
    application_sessions_dir: str = "../data/application_sessions"
    field_confidence_high: float = 0.90
    field_confidence_medium: float = 0.70

    # Step 6: job-search tracking, analytics, and follow-up management.
    # A suggested follow-up date is only ever a suggestion -- the user
    # must explicitly create it (spec section 12); nothing is scheduled
    # automatically.
    default_followup_days: int = 7
    timezone: str = "UTC"

    # Step 2b: job discovery. Greenhouse/Lever/RemoteOK/WWR/Remotive/
    # Arbeitnow/Himalayas need no key at all; Adzuna and USAJobs are free
    # but keyed -- leave their keys blank to simply skip those two sources
    # (reported, not a hard failure). LinkedIn/Indeed/SimplyHired/Wellfound
    # are deliberately absent: all four prohibit automated scraping in
    # their ToS, so they stay a manual paste/URL flow (Step 2).
    discovery_enabled_sources: list[str] = [
        "greenhouse", "lever", "remoteok", "weworkremotely", "adzuna", "usajobs",
        "remotive", "arbeitnow", "himalayas",
    ]
    discovery_max_results_per_source: int = 25
    adzuna_app_id: str = ""
    adzuna_app_key: str = ""
    adzuna_country: str = "us"
    usajobs_api_key: str = ""
    usajobs_user_agent_email: str = ""
    # Background scheduled discovery runs, in addition to on-demand
    # POST /discovery/run calls. Disabled by default -- discovery only
    # ever runs when you explicitly ask it to, until you opt in here.
    discovery_scheduler_enabled: bool = False
    discovery_scheduler_interval_hours: int = 24

    # Step 8: AI job search agent / orchestrator. Conservative defaults on
    # purpose (spec section 62) -- the agent can search/analyze/rank/
    # generate/prepare on its own, but never submits an application or
    # sends any external message without a separate, explicit approval.
    # Reuses the existing `dry_run` flag (Step 5) as the hard submission
    # gate rather than introducing a second identical setting.
    agent_enabled: bool = True
    max_agent_steps: int = 20
    max_agent_retries: int = 2
    auto_generate_materials: bool = True
    auto_prepare_applications: bool = True
    auto_submit_applications: bool = False
    auto_send_messages: bool = False
    require_approval_for_external_actions: bool = True

    # Frontend (React/Vite dev server). Only used to configure CORS --
    # the dev server itself proxies /api requests same-origin, so this
    # mainly matters if you call the API directly from the browser (e.g.
    # the built frontend served separately, or a different dev port).
    frontend_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]

    model_config = SettingsConfigDict(env_file=".env", env_prefix="", case_sensitive=False)


@lru_cache
def get_settings() -> Settings:
    return Settings()
