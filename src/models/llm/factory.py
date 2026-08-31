"""Provider selection: `get_llm("gemini")` / `get_llm("ollama")` / `get_llm()`."""
from src.config import Settings, get_settings
from src.models.llm.base import LLMProvider
from src.models.llm.gemini import GeminiProvider
from src.models.llm.ollama import OllamaProvider

PROVIDERS: dict[str, type[LLMProvider]] = {
    "gemini": GeminiProvider,
    "ollama": OllamaProvider,
}


def get_llm(name: str | None = None, *, settings: Settings | None = None) -> LLMProvider:
    settings = settings or get_settings()
    provider_name = name or settings.llm_provider

    if provider_name not in PROVIDERS:
        available = ", ".join(sorted(PROVIDERS))
        raise ValueError(f"Unknown LLM provider {provider_name!r}. Available: {available}")

    if provider_name == "gemini":
        api_key = (
            settings.openrouter_api_key.get_secret_value()
            if settings.openrouter_api_key
            else None
        )
        return GeminiProvider(api_key=api_key, model=settings.gemini_model)

    return OllamaProvider(base_url=settings.ollama_base_url, model=settings.ollama_model)
