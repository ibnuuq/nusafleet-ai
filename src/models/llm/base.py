"""LLM provider abstraction.

Every provider implements the same async contract so the orchestrator can
swap Gemini <-> Ollama without caring which one it's talking to. Constructors
must not touch the network or require credentials -- validation happens at
`generate()` time, so providers can be instantiated freely in tests.
"""
from abc import ABC, abstractmethod
from typing import Any, ClassVar

from pydantic import BaseModel


class LLMError(RuntimeError):
    """Raised when a provider fails to produce a response.

    Base of a small hierarchy so callers (M4+ orchestrator) can catch a
    specific failure mode across providers without caring which provider
    raised it. Subclasses below are shared where the failure mode is
    provider-agnostic (timeout, malformed response, unknown model); rate
    limit / quota are OpenRouter-specific today but live in the same
    hierarchy for a uniform `except` surface.
    """


class LLMTimeoutError(LLMError):
    """The request exceeded the configured timeout."""


class LLMResponseError(LLMError):
    """The provider returned HTTP 200 but the body was empty or malformed
    (e.g. missing `choices`/`message` structure). Distinct from a
    legitimately empty completion, which is not an error."""


class LLMModelNotFoundError(LLMError):
    """The requested model id/slug is not available at the provider."""


class LLMRateLimitError(LLMError):
    """The provider is rate-limiting requests (e.g. HTTP 429)."""


class LLMQuotaExceededError(LLMError):
    """The provider account lacks credits/quota (e.g. OpenRouter HTTP 402)."""


class LLMMessage(BaseModel):
    role: str
    content: str


class LLMResponse(BaseModel):
    text: str
    provider: str
    model: str
    usage: dict[str, int] = {}
    raw: dict[str, Any] | None = None


class LLMProvider(ABC):
    name: ClassVar[str]

    @abstractmethod
    async def generate(
        self,
        prompt: str,
        *,
        system: str | None = None,
        temperature: float = 0.2,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        """Generate a completion for `prompt`. Raises LLMError on failure."""

    @abstractmethod
    async def health_check(self) -> bool:
        """Return True if the provider is currently reachable/usable."""
