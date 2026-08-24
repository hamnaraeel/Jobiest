import logging

import requests
from openai import OpenAI
from pydantic import BaseModel

from app.config import get_settings

logger = logging.getLogger("app.ai.client")

# Groq's gpt-oss-* models are reasoning models that spend tokens on hidden
# reasoning before emitting the actual JSON -- without an explicit budget,
# Groq's own low default cuts that off mid-object and
# `.chat.completions.parse()` fails with a generic "Failed to validate
# JSON" (empty failed_generation). This free-tier Groq key is additionally
# capped at 8000 tokens/minute *total* (prompt + max_tokens) per request,
# so the budget below is kept well under that even for a sizeable
# resume/job-description prompt. OpenAI's non-reasoning models don't need
# this much, but accept the same param.
STRUCTURED_OUTPUT_MAX_TOKENS = 4500


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


def get_groq_client() -> OpenAI:
    """Groq hosts full-size open models behind an OpenAI-compatible
    endpoint, so the OpenAI SDK works unmodified -- just a different
    base_url and key. Free tier; used in place of OpenAI when
    AI_PROVIDER=groq (see get_ai_client)."""
    settings = get_settings()
    if not settings.groq_api_key:
        raise AIConfigurationError(
            "GROQ_API_KEY is not set. AI_PROVIDER=groq requires a Groq API key -- create "
            "a free one at https://console.groq.com and set GROQ_API_KEY in your .env."
        )
    return OpenAI(api_key=settings.groq_api_key, base_url=settings.groq_base_url)


def get_ai_client() -> OpenAI:
    """Steps 2-3/1b (JD analysis, matching, CV customization, resume
    parsing) call this instead of get_openai_client() directly, so
    AI_PROVIDER is the one setting that decides which OpenAI-compatible
    backend they hit. Pair with get_ai_model() for the matching model
    name."""
    settings = get_settings()
    if settings.ai_provider == "groq":
        return get_groq_client()
    return get_openai_client()


def get_ai_extra_params() -> dict:
    """Provider-specific kwargs to splat into `.chat.completions.parse()`
    calls. Groq's gpt-oss models default to spending most of the token
    budget on hidden reasoning (see STRUCTURED_OUTPUT_MAX_TOKENS) --
    `reasoning_effort="low"` keeps that in check so the visible JSON
    reliably fits within budget. OpenAI's models don't accept this param
    for chat.completions, so it's Groq-only."""
    settings = get_settings()
    if settings.ai_provider == "groq":
        return {"reasoning_effort": "low"}
    return {}


def get_ai_model() -> str:
    settings = get_settings()
    return settings.groq_model if settings.ai_provider == "groq" else settings.openai_model


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

    def __init__(self, base_url: str, model: str, timeout: float = 300.0):
        # CPU-only local inference on modest hardware: structured (schema-
        # constrained) generation over a full resume/job-description
        # prompt reliably takes 1-2 minutes even on a small model, well
        # past a naive 120s default -- 300s gives real headroom without
        # hanging forever on a genuinely dead Ollama server.
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
