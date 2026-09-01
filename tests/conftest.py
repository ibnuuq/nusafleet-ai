"""Shared fixtures and test helpers.

`isolated_settings` builds a Settings instance from a known dummy env,
ignoring whatever real `.env` is present on disk -- most tests must not
depend on real credentials or a live Postgres/Ollama/OpenRouter. The
exception is tests/test_llm_live.py and tests/test_tools.py, which
deliberately read the real `.env` -- that's the point of a live smoke
test.
"""
from contextlib import contextmanager
from typing import Callable

import httpx
import psycopg2
import pytest

from src.config import Settings, get_settings


@pytest.fixture
def isolated_settings() -> Settings:
    return Settings(
        _env_file=None,
        APP_ENV="test",
        LOG_LEVEL="DEBUG",
        LLM_PROVIDER="ollama",
        OPENROUTER_API_KEY=None,
        OLLAMA_BASE_URL="http://localhost:11434",
        OLLAMA_MODEL="test-model",
    )


@contextmanager
def mock_httpx_transport(module, handler: Callable[[httpx.Request], httpx.Response]):
    """Make every `httpx.AsyncClient` built inside `module` route through
    `handler` instead of the network. `module` is the provider module
    (e.g. `src.models.llm.ollama`), which the provider itself imports
    `httpx` into -- patching `module.httpx.AsyncClient` is what actually
    intercepts the client the provider constructs.
    """
    original = module.httpx.AsyncClient

    def patched(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return original(*args, **kwargs)

    module.httpx.AsyncClient = patched
    try:
        yield
    finally:
        module.httpx.AsyncClient = original


@pytest.fixture(scope="session")
def require_ro_database() -> None:
    """Skip (never fail) a test that needs a real, reachable
    `nusafleet_ro` connection, with a message explaining exactly why --
    mirrors the skip pattern in tests/test_llm_live.py for OpenRouter/
    Ollama. Checked via a real `Settings()`, so a value in `.env` counts.
    """
    settings = get_settings()
    if not settings.database_url_ro:
        pytest.skip("DATABASE_URL_RO not set in environment/.env -- skipping live database test")
    try:
        conn = psycopg2.connect(settings.database_url_ro.get_secret_value(), connect_timeout=3)
        conn.close()
    except psycopg2.OperationalError as exc:
        pytest.skip(f"DATABASE_URL_RO not reachable ({exc}) -- skipping live database test")
