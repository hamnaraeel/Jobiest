from openai import OpenAI

from app.config import get_settings


class AIConfigurationError(RuntimeError):
    """Raised when an AI-powered feature is used without OPENAI_API_KEY
    configured. Callers (API routers) should turn this into a clear 4xx
    response rather than letting it surface as an opaque 500."""


def get_openai_client() -> OpenAI:
    settings = get_settings()
    if not settings.openai_api_key:
        raise AIConfigurationError(
            "OPENAI_API_KEY is not set. AI-powered job analysis requires an OpenAI API "
            "key -- set OPENAI_API_KEY in your .env to use this feature. Job storage, "
            "cleaning, and dashboard browsing work without it."
        )
    return OpenAI(api_key=settings.openai_api_key)
