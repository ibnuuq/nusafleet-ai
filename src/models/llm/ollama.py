"""Ollama provider -- talks directly to the local Ollama HTTP API via httpx.

No `ollama` package dependency: the HTTP surface is small enough that a raw
client keeps the dependency footprint down.
"""
import httpx

from src.models.llm.base import (
    LLMError,
    LLMModelNotFoundError,
    LLMProvider,
    LLMResponse,
    LLMResponseError,
    LLMTimeoutError,
)


class OllamaProvider(LLMProvider):
    name = "ollama"

    def __init__(self, base_url: str, model: str, timeout: float = 60.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout = timeout

    async def generate(
        self,
        prompt: str,
        *,
        system: str | None = None,
        temperature: float = 0.2,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        payload: dict = {
            "model": self._model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": temperature},
        }
        if max_tokens is not None:
            payload["options"]["num_predict"] = max_tokens

        try:
            async with httpx.AsyncClient(base_url=self._base_url, timeout=self._timeout) as client:
                resp = await client.post("/api/chat", json=payload)
        except httpx.TimeoutException as exc:
            raise LLMTimeoutError(f"Ollama request timed out: {exc}") from exc
        except httpx.HTTPError as exc:
            raise LLMError(f"Ollama request failed: {exc}") from exc

        if resp.status_code == 404:
            raise LLMModelNotFoundError(f"Ollama model not found: {resp.text}")
        try:
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise LLMError(f"Ollama request failed: {exc}") from exc

        try:
            data = resp.json()
        except ValueError as exc:
            raise LLMResponseError(f"Ollama returned a non-JSON body: {exc}") from exc

        try:
            text = data["message"]["content"]
        except (KeyError, TypeError) as exc:
            raise LLMResponseError(
                f"Ollama response missing message.content: {data!r}"
            ) from exc

        return LLMResponse(
            text=text,
            provider=self.name,
            model=self._model,
            usage={
                "prompt_tokens": data.get("prompt_eval_count", 0),
                "completion_tokens": data.get("eval_count", 0),
            },
            raw=data,
        )

    async def health_check(self) -> bool:
        try:
            async with httpx.AsyncClient(base_url=self._base_url, timeout=5.0) as client:
                resp = await client.get("/api/tags")
                return resp.status_code == 200
        except httpx.HTTPError:
            return False
