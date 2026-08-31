"""Live smoke tests -- these hit a real external endpoint.

Both auto-SKIP (never fail) when their prerequisite isn't available:
  - OpenRouter: skipped if OPENROUTER_API_KEY isn't set (checked via a real
    `Settings()`, so a value in `.env` counts).
  - Ollama: skipped if the configured Ollama instance isn't reachable.

Deliberately not using `isolated_settings` here -- the whole point is to
exercise the real configured credentials/endpoints. Deselect this whole
file with `pytest -m "not live"` to avoid live API calls/cost on a normal
run.
"""
import pytest

from src.config import Settings
from src.models.llm.gemini import GeminiProvider
from src.models.llm.ollama import OllamaProvider

pytestmark = pytest.mark.live


@pytest.mark.asyncio
async def test_gemini_generate_live_via_openrouter():
    settings = Settings()
    if not settings.openrouter_api_key:
        pytest.skip("OPENROUTER_API_KEY not set in environment/.env -- skipping live OpenRouter smoke test")

    provider = GeminiProvider(
        api_key=settings.openrouter_api_key.get_secret_value(),
        model=settings.gemini_model,
    )
    response = await provider.generate("Reply with exactly one word: pong", max_tokens=16)

    assert response.text.strip()
    assert response.provider == "gemini"
    assert response.model == settings.gemini_model


@pytest.mark.asyncio
async def test_ollama_generate_live():
    settings = Settings()
    provider = OllamaProvider(base_url=settings.ollama_base_url, model=settings.ollama_model)

    if not await provider.health_check():
        pytest.skip(f"Ollama not reachable at {settings.ollama_base_url} -- skipping live smoke test")

    response = await provider.generate("Reply with exactly one word: pong", max_tokens=16)

    assert response.text.strip()
    assert response.provider == "ollama"
