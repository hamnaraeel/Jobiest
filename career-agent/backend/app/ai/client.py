import logging

import requests
from openai import OpenAI
from pydantic import BaseModel

from app.config import get_settings

logger = logging.getLogger("app.ai.client")


class AIConfigurationError(RuntimeError):
    """Raised when an AI-powered feature is used without its provider
    configured (OPENAI_API_KEY for OpenAI-backed features, OLLAMA_MODEL
    for local-only ones). Callers (API routers) should turn this into a
    clear 4xx response rather than letting it surface as an opaque 500."""


def get_openai_client() -> OpenAI:
    settings = get_settings()
    if not settings.openai_api_key:
        raise AIConfigurationError(
            "OPENAI_API_KEY is not set. AI-powered job analysis requires an OpenAI API "
            "key -- set OPENAI_API_KEY in your .env to use this feature. Job storage, "
            "cleaning, and dashboard browsing work without it."
        )
    return OpenAI(api_key=settings.openai_api_key)


class OllamaResponseError(RuntimeError):
    """Ollama reached, but its response didn't parse as valid structured
    output -- distinct from AIConfigurationError (which means Ollama or
    the model isn't reachable/configured at all)."""


class OllamaClient:
    """Thin wrapper around Ollama's REST API (`/api/chat`), used instead
    of the OpenAI SDK for Step 4's cover-letter and application-answer
    generation -- no paid API, no API key, entirely local. Ollama's
    `format` field accepts a JSON schema directly (constrained decoding),
    which is how structured output is enforced here without needing
    OpenAI's SDK-specific `.chat.completions.parse()` helper."""

    def __init__(self, base_url: str, model: str, timeout: float = 120.0):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout

    def chat_structured(self, system_prompt: str, user_content: str, schema: type[BaseModel]) -> BaseModel:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            "format": schema.model_json_schema(),
            "stream": False,
            "options": {"temperature": 0.2},
        }

        try:
            response = requests.post(f"{self.base_url}/api/chat", json=payload, timeout=self.timeout)
        except requests.RequestException as exc:
            raise AIConfigurationError(
                f"Cannot reach Ollama at {self.base_url}: {exc}. Is Ollama running? "
                f"Try `ollama serve` (or `brew services start ollama`)."
            ) from exc

        if response.status_code == 404:
            raise AIConfigurationError(
                f"Ollama model '{self.model}' was not found. Try `ollama pull {self.model}` first."
            )
        if response.status_code >= 400:
            raise AIConfigurationError(f"Ollama returned HTTP {response.status_code}: {response.text[:300]}")

        try:
            content = response.json()["message"]["content"]
            return schema.model_validate_json(content)
        except (KeyError, ValueError) as exc:
            logger.warning("ollama structured output failed to parse: %s", exc)
            raise OllamaResponseError(f"Ollama response did not match the expected schema: {exc}") from exc


def call_ollama_structured(
    client: OllamaClient, system_prompt: str, user_content: str, schema: type[BaseModel], max_retries: int = 1
) -> BaseModel:
    """Shared by cover_letter_service and application_answer_service so
    the "retry once on malformed output" policy (spec: max 2 attempts)
    lives in one place. This retries on schema/parse failures only --
    domain-level validation retries (e.g. an unsupported claim) are a
    separate, higher-level concern handled by the calling service, same
    split as cv_customization_service's two independent retry loops."""

    last_error = "unknown error"
    content = user_content

    for attempt in range(max_retries + 1):
        try:
            return client.chat_structured(system_prompt, content, schema)
        except OllamaResponseError as exc:
            last_error = str(exc)
            if attempt < max_retries:
                logger.warning("ollama structured call failed (attempt %d), retrying: %s", attempt + 1, last_error)
                content = f"{user_content}\n\nYour previous response was invalid: {last_error}. Strictly follow the required JSON schema and try again."

    raise OllamaResponseError(last_error)


def get_ollama_client() -> OllamaClient:
    settings = get_settings()
    if not settings.ollama_model:
        raise AIConfigurationError(
            "OLLAMA_MODEL is not set. Cover letter and application-answer generation run "
            "entirely on a local Ollama model -- set OLLAMA_MODEL in your .env (and run "
            "`ollama pull <model>`) to use this feature."
        )
    return OllamaClient(base_url=settings.ollama_base_url, model=settings.ollama_model)
