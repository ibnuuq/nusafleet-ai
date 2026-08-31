"""Gemini provider -- calls Gemini via OpenRouter (OpenAI-compatible HTTP),
not the native `google-genai` SDK.

The class name and `get_llm("gemini")` selector are unchanged from M1 --
what changed is only the backend: the credential available to this project
is an OpenRouter key, not a native Google AI Studio key, and the two are not
interchangeable. See docs/architecture/m1_foundation.md ("Why GeminiProvider
calls openrouter.ai") for the full rationale.

The client never touches the network in `__init__`; a missing/invalid API
key only surfaces as an `LLMError` at `generate()` time, same as M1.
"""
import httpx

from src.models.llm.base import (
    LLMError,
    LLMModelNotFoundError,
    LLMProvider,
    LLMQuotaExceededError,
    LLMRateLimitError,
    LLMResponse,
    LLMResponseError,
    LLMTimeoutError,
)

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


class GeminiProvider(LLMProvider):
    name = "gemini"

    def __init__(
        self,
        api_key: str | None,
        model: str,
        base_url: str = OPENROUTER_BASE_URL,
        timeout: float = 60.0,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    async def generate(
        self,
        prompt: str,
        *,
        system: str | None = None,
        temperature: float = 0.2,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        if not self._api_key:
            raise LLMError("OPENROUTER_API_KEY is not set")

        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        payload: dict = {
            "model": self._model,
            "messages": messages,
            "temperature": temperature,
        }
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens

        headers = {"Authorization": f"Bearer {self._api_key}"}

        try:
            async with httpx.AsyncClient(base_url=self._base_url, timeout=self._timeout) as client:
                resp = await client.post("/chat/completions", json=payload, headers=headers)
        except httpx.TimeoutException as exc:
            raise LLMTimeoutError(f"OpenRouter request timed out: {exc}") from exc
        except httpx.HTTPError as exc:
            raise LLMError(f"OpenRouter request failed: {exc}") from exc

        try:
            data = resp.json()
        except ValueError as exc:
            raise LLMResponseError(f"OpenRouter returned a non-JSON body: {exc}") from exc

        if resp.status_code != 200 or "error" in data:
            _raise_for_openrouter_error(resp.status_code, data)

        try:
            choice = data["choices"][0]
            text = choice["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMResponseError(
                f"OpenRouter response missing choices/message.content: {data!r}"
            ) from exc

        usage = data.get("usage") or {}
        return LLMResponse(
            text=text or "",
            provider=self.name,
            model=self._model,
            usage={
                "prompt_tokens": usage.get("prompt_tokens", 0),
                "completion_tokens": usage.get("completion_tokens", 0),
            },
            raw=data,
        )

    async def health_check(self) -> bool:
        if not self._api_key:
            return False
        try:
            async with httpx.AsyncClient(base_url=self._base_url, timeout=5.0) as client:
                resp = await client.get(
                    "/models", headers={"Authorization": f"Bearer {self._api_key}"}
                )
                return resp.status_code == 200
        except httpx.HTTPError:
            return False


def _raise_for_openrouter_error(status_code: int, data: dict) -> None:
    """Map an OpenRouter error body (`{"error": {"code", "message", ...}}`)
    to the shared LLM exception hierarchy. Always raises."""
    error = data.get("error") or {}
    message = error.get("message") or f"OpenRouter request failed with status {status_code}"

    if status_code == 402:
        raise LLMQuotaExceededError(f"OpenRouter insufficient credits: {message}")
    if status_code == 429:
        raise LLMRateLimitError(f"OpenRouter rate limit exceeded: {message}")
    if status_code == 404 or (status_code == 400 and "model" in message.lower()):
        raise LLMModelNotFoundError(f"OpenRouter model not found: {message}")
    raise LLMError(f"OpenRouter request failed ({status_code}): {message}")
