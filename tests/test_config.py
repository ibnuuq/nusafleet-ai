import pytest
from pydantic import ValidationError

from src.config import Settings


def test_defaults_when_env_empty():
    s = Settings(_env_file=None)
    assert s.llm_provider == "ollama"
    assert s.app_env == "dev"
    assert s.database_url_ro is None


def test_env_override(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    monkeypatch.setenv("APP_ENV", "prod")
    s = Settings(_env_file=None)
    assert s.llm_provider == "gemini"
    assert s.app_env == "prod"


def test_invalid_provider_rejected():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, LLM_PROVIDER="chatgpt")


def test_invalid_app_env_rejected():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, APP_ENV="staging")


def test_secret_not_leaked_in_repr():
    s = Settings(_env_file=None, OPENROUTER_API_KEY="super-secret-value")
    assert "super-secret-value" not in repr(s)
    assert "super-secret-value" not in str(s)


def test_gemini_model_defaults_to_openrouter_slug():
    """GeminiProvider calls OpenRouter, so the default model must be an
    OpenRouter-style slug (vendor/model), not a bare native model name."""
    s = Settings(_env_file=None)
    assert s.gemini_model == "google/gemini-2.5-flash"


def test_settings_has_no_admin_database_field():
    """Guardrail: Settings must never grow a write/admin DSN field."""
    assert "database_url" not in Settings.model_fields
    assert "database_url_ro" in Settings.model_fields
