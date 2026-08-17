from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg2://postgres:postgres@localhost:5432/career_agent"
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"

    cv_max_pages: int = 1
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

    # Frontend (React/Vite dev server). Only used to configure CORS --
    # the dev server itself proxies /api requests same-origin, so this
    # mainly matters if you call the API directly from the browser (e.g.
    # the built frontend served separately, or a different dev port).
    frontend_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]

    model_config = SettingsConfigDict(env_file=".env", env_prefix="", case_sensitive=False)


@lru_cache
def get_settings() -> Settings:
    return Settings()
