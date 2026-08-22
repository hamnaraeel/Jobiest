"""get_ai_client()/get_ai_model() (app/ai/client.py) are the one switch
that decides whether Steps 2-3/1b hit OpenAI or Groq's OpenAI-compatible
free tier -- covered here directly since the per-service tests mock this
wrapper away entirely and never exercise its own branching."""

import pytest

from app.ai.client import AIConfigurationError, get_ai_client, get_ai_model
from app.config import Settings


def _settings(**overrides) -> Settings:
    defaults = dict(openai_api_key="", groq_api_key="", ai_provider="openai")
    defaults.update(overrides)
    return Settings(**defaults)


def test_default_provider_uses_openai(mocker):
    mocker.patch("app.ai.client.get_settings", return_value=_settings(openai_api_key="sk-test"))
    client = get_ai_client()
    assert client.base_url is not None
    assert "api.openai.com" in str(client.base_url)


def test_default_provider_model_is_openai_model(mocker):
    mocker.patch("app.ai.client.get_settings", return_value=_settings(openai_api_key="sk-test", openai_model="gpt-4o-mini"))
    assert get_ai_model() == "gpt-4o-mini"


def test_groq_provider_uses_groq_base_url(mocker):
    mocker.patch("app.ai.client.get_settings", return_value=_settings(ai_provider="groq", groq_api_key="gsk-test"))
    client = get_ai_client()
    assert "api.groq.com" in str(client.base_url)


def test_groq_provider_model_is_groq_model(mocker):
    mocker.patch(
        "app.ai.client.get_settings",
        return_value=_settings(ai_provider="groq", groq_api_key="gsk-test", groq_model="openai/gpt-oss-120b"),
    )
    assert get_ai_model() == "openai/gpt-oss-120b"


def test_groq_provider_without_key_raises_configuration_error(mocker):
    mocker.patch("app.ai.client.get_settings", return_value=_settings(ai_provider="groq", groq_api_key=""))
    with pytest.raises(AIConfigurationError):
        get_ai_client()


def test_openai_provider_without_key_raises_configuration_error(mocker):
    mocker.patch("app.ai.client.get_settings", return_value=_settings(ai_provider="openai", openai_api_key=""))
    with pytest.raises(AIConfigurationError):
        get_ai_client()
