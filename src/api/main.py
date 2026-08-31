"""M1 entry point stub.

Loads config, sets up logging, confirms the skeleton is wired correctly, and
exits. No HTTP server -- that's M2+ scope. Kept runnable via
`python -m src.api.main` because docker-compose.yml already invokes it that
way.
"""
from src.config import get_settings
from src.logging_config import configure_logging, get_logger


def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    log = get_logger(__name__)
    log.info(
        "nusafleet-ai M1 skeleton ready (env=%s, llm_provider=%s)",
        settings.app_env,
        settings.llm_provider,
    )


if __name__ == "__main__":
    main()
