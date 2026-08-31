"""Application configuration.

Loaded from environment variables / `.env`. Deliberately has no field that can
resolve to an admin/write database DSN or to any ground-truth location --
see docs/architecture/m1_foundation.md for the isolation rationale.
"""
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

LLMProviderName = Literal["gemini", "ollama"]

# --- artifact_dir guardrail -------------------------------------------------
# This is the one deliberate, narrow exception to "src/ never names
# ground-truth locations": a denylist that exists solely to REJECT an
# `artifact_dir` that would resolve into one of them. It never reads, joins,
# or otherwise turns those paths into something readable -- only into a
# ValueError. tests/test_ground_truth_isolation.py excludes this file from
# its literal-substring scan for exactly this reason (a rejection rule can't
# avoid naming what it rejects), and separately verifies the rejection
# actually fires for representative paths and traversals. This is defense in
# depth on top of the allowlist model (artifact_dir defaults to a workspace
# subfolder); it does not replace it. See docs/architecture/m1_foundation.md.
_REPO_ROOT = Path(__file__).resolve().parent.parent
_GROUND_TRUTH_DIRS = tuple(
    (_REPO_ROOT / segments[0]).joinpath(*segments[1:]).resolve()
    for segments in (
        ("docs", "internal"),
        ("eval", "reference"),
        ("eval", "internal"),
        ("verification",),
    )
)


def _resolves_into_ground_truth(candidate: Path) -> bool:
    for marker in _GROUND_TRUTH_DIRS:
        if candidate == marker or candidate.is_relative_to(marker) or marker.is_relative_to(candidate):
            return True
    return False


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_env: Literal["dev", "test", "prod"] = Field(default="dev", alias="APP_ENV")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    llm_provider: LLMProviderName = Field(default="ollama", alias="LLM_PROVIDER")

    # GeminiProvider calls OpenRouter (OpenAI-compatible), not the native
    # Gemini API -- see docs/architecture/m1_foundation.md ("Why
    # GeminiProvider calls openrouter.ai"). Field name follows the
    # credential actually in use.
    openrouter_api_key: SecretStr | None = Field(default=None, alias="OPENROUTER_API_KEY")
    gemini_model: str = Field(default="google/gemini-2.5-flash", alias="GEMINI_MODEL")

    ollama_base_url: str = Field(default="http://localhost:11434", alias="OLLAMA_BASE_URL")
    ollama_model: str = Field(default="qwen2.5:14b-instruct", alias="OLLAMA_MODEL")

    # Read-only database access only. There is intentionally no admin/write
    # DSN field here -- see docs/architecture/m1_foundation.md.
    database_url_ro: SecretStr | None = Field(default=None, alias="DATABASE_URL_RO")

    # Allowlisted runtime working directory for agent-produced artifacts.
    # Ground-truth folders are never reachable through this setting -- the
    # validator below rejects any value that resolves into one.
    artifact_dir: Path = Field(default=Path("./artifacts"), alias="ARTIFACT_DIR")

    @field_validator("artifact_dir")
    @classmethod
    def _artifact_dir_must_not_reach_ground_truth(cls, value: Path) -> Path:
        candidate = value if value.is_absolute() else _REPO_ROOT / value
        candidate = candidate.resolve()
        if _resolves_into_ground_truth(candidate):
            raise ValueError(
                f"artifact_dir resolves into a ground-truth location ({candidate}); "
                "see docs/internal/README_ISOLATION.md"
            )
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
