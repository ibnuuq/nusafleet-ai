"""Unit tests for both providers. Everything here runs fully offline via
`httpx.MockTransport` (see `mock_httpx_transport` in conftest.py) -- no real
network call, no real credentials. Live-network smoke tests live in
tests/test_llm_live.py.
"""
import httpx
import pytest

import src.models.llm.gemini as gemini_module
import src.models.llm.ollama as ollama_module
from src.config import Settings
from src.models.llm import (
    LLMError,
    LLMModelNotFoundError,
    LLMQuotaExceededError,
    LLMRateLimitError,
    LLMResponseError,
    LLMTimeoutError,
    get_llm,
)
from src.models.llm.gemini import GeminiProvider
from src.models.llm.ollama import OllamaProvider
from tests.conftest import mock_httpx_transport


def test_get_llm_unknown_provider_raises(isolated_settings: Settings):
    with pytest.raises(ValueError, match="Unknown LLM provider"):
        get_llm("chatgpt", settings=isolated_settings)


def test_get_llm_defaults_to_settings_provider(isolated_settings: Settings):
    provider = get_llm(settings=isolated_settings)
    assert isinstance(provider, OllamaProvider)


# --- GeminiProvider (OpenRouter backend) ------------------------------------


@pytest.mark.asyncio
async def test_gemini_generate_without_api_key_raises_at_call_time():
    provider = GeminiProvider(api_key=None, model="google/gemini-2.5-flash")
    # Instantiation must not have raised. Only generate() should.
    with pytest.raises(LLMError):
        await provider.generate("hello")


@pytest.mark.asyncio
async def test_gemini_health_check_false_without_api_key():
    provider = GeminiProvider(api_key=None, model="google/gemini-2.5-flash")
    assert await provider.health_check() is False


@pytest.mark.asyncio
async def test_gemini_generate_success_via_mock_transport():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/chat/completions"
        assert request.headers["authorization"] == "Bearer test-key"
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"role": "assistant", "content": "hi from gemini"}}],
                "usage": {"prompt_tokens": 7, "completion_tokens": 3},
            },
        )

    provider = GeminiProvider(
        api_key="test-key", model="google/gemini-2.5-flash", base_url="http://openrouter.test"
    )
    with mock_httpx_transport(gemini_module, handler):
        response = await provider.generate("hello", system="be terse")

    assert response.text == "hi from gemini"
    assert response.provider == "gemini"
    assert response.model == "google/gemini-2.5-flash"
    assert response.usage == {"prompt_tokens": 7, "completion_tokens": 3}


@pytest.mark.asyncio
async def test_gemini_generate_insufficient_credits_raises_quota_exceeded():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            402, json={"error": {"code": 402, "message": "Insufficient credits"}}
        )

    provider = GeminiProvider(
        api_key="test-key", model="google/gemini-2.5-flash", base_url="http://openrouter.test"
    )
    with mock_httpx_transport(gemini_module, handler):
        with pytest.raises(LLMQuotaExceededError):
            await provider.generate("hello")


@pytest.mark.asyncio
async def test_gemini_generate_rate_limited_raises_rate_limit_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            429, json={"error": {"code": 429, "message": "Rate limit exceeded"}}
        )

    provider = GeminiProvider(
        api_key="test-key", model="google/gemini-2.5-flash", base_url="http://openrouter.test"
    )
    with mock_httpx_transport(gemini_module, handler):
        with pytest.raises(LLMRateLimitError):
            await provider.generate("hello")


@pytest.mark.asyncio
async def test_gemini_generate_unknown_model_raises_model_not_found():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            404,
            json={"error": {"code": 404, "message": "No endpoints found for model foo/bar"}},
        )

    provider = GeminiProvider(
        api_key="test-key", model="foo/bar", base_url="http://openrouter.test"
    )
    with mock_httpx_transport(gemini_module, handler):
        with pytest.raises(LLMModelNotFoundError):
            await provider.generate("hello")


@pytest.mark.asyncio
async def test_gemini_generate_malformed_response_raises_response_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"unexpected": "shape"})

    provider = GeminiProvider(
        api_key="test-key", model="google/gemini-2.5-flash", base_url="http://openrouter.test"
    )
    with mock_httpx_transport(gemini_module, handler):
        with pytest.raises(LLMResponseError):
            await provider.generate("hello")


@pytest.mark.asyncio
async def test_gemini_generate_timeout_raises_timeout_error():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("simulated timeout", request=request)

    provider = GeminiProvider(
        api_key="test-key", model="google/gemini-2.5-flash", base_url="http://openrouter.test"
    )
    with mock_httpx_transport(gemini_module, handler):
        with pytest.raises(LLMTimeoutError):
            await provider.generate("hello")


# --- OllamaProvider ----------------------------------------------------------


@pytest.mark.asyncio
async def test_ollama_generate_uses_mock_transport():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/chat"
        return httpx.Response(
            200,
            json={
                "message": {"role": "assistant", "content": "hi there"},
                "prompt_eval_count": 3,
                "eval_count": 5,
            },
        )

    provider = OllamaProvider(base_url="http://ollama.test", model="test-model")
    with mock_httpx_transport(ollama_module, handler):
        response = await provider.generate("hello", system="be terse")

    assert response.text == "hi there"
    assert response.provider == "ollama"
    assert response.usage == {"prompt_tokens": 3, "completion_tokens": 5}


@pytest.mark.asyncio
async def test_ollama_generate_wraps_generic_http_errors():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "boom"})

    provider = OllamaProvider(base_url="http://ollama.test", model="test-model")
    with mock_httpx_transport(ollama_module, handler):
        with pytest.raises(LLMError):
            await provider.generate("hello")


@pytest.mark.asyncio
async def test_ollama_generate_unknown_model_raises_model_not_found():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"error": 'model "nope" not found, try pulling it first'})

    provider = OllamaProvider(base_url="http://ollama.test", model="nope")
    with mock_httpx_transport(ollama_module, handler):
        with pytest.raises(LLMModelNotFoundError):
            await provider.generate("hello")


@pytest.mark.asyncio
async def test_ollama_generate_malformed_response_raises_response_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"unexpected": "shape"})

    provider = OllamaProvider(base_url="http://ollama.test", model="test-model")
    with mock_httpx_transport(ollama_module, handler):
        with pytest.raises(LLMResponseError):
            await provider.generate("hello")


@pytest.mark.asyncio
async def test_ollama_generate_timeout_raises_timeout_error():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("simulated timeout", request=request)

    provider = OllamaProvider(base_url="http://ollama.test", model="test-model")
    with mock_httpx_transport(ollama_module, handler):
        with pytest.raises(LLMTimeoutError):
            await provider.generate("hello")
