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

    model_config = SettingsConfigDict(env_file=".env", env_prefix="", case_sensitive=False)


@lru_cache
def get_settings() -> Settings:
    return Settings()
