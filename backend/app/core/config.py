"""Application configuration.

All runtime configuration comes from environment variables (or a local
`.env` file during development). Nothing sensitive is ever hard-coded.

Pydantic Settings gives us:
  * type validation of every value at startup (fail fast, not mid-request)
  * a single, importable source of truth for configuration
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings for the NISH backend."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",  # unknown env vars are not an error
    )

    # --- Application ---
    app_name: str = "NISH"
    environment: str = "development"  # development | production
    api_prefix: str = "/api"

    # --- CORS ---
    # Comma-separated list of origins allowed to call this API from a browser.
    cors_origins: str = "http://localhost:3000"

    # --- Identity ---
    # Path to the identity configuration (public app facts only —
    # never put secrets in this file).
    identity_config_path: str = "./identity.json"

    # --- Database ---
    # Full SQLAlchemy URL. Compose and .env.example use a local Postgres;
    # tests override this with SQLite. No credentials are hard-coded here
    # beyond a development default that matches docker-compose.
    database_url: str = "postgresql+psycopg://nish:nish@localhost:5432/nish"

    # --- Ollama ---
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen3:8b"
    # Hard ceiling on how long we wait for a full (non-streaming) completion.
    ollama_timeout_seconds: float = 120.0

    # --- Request limits (basic input validation / abuse protection) ---
    max_message_chars: int = 8_000     # per single message
    max_history_messages: int = 40     # per request

    # --- Agent (autonomous coding) ---
    # The ONLY directory tree the agent may read. Everything outside it is
    # denied by PathGuard, no exceptions. Point this at the project you
    # want NISH to work on.
    agent_workspace_root: str = "./workspace"
    # Append-only audit log (JSONL, hash-chained).
    agent_audit_log_path: str = "./audit/agent-audit.jsonl"
    # Read limits: keep prompts bounded and prevent huge-file abuse.
    agent_max_read_bytes: int = 256_000        # per file read
    agent_max_tree_entries: int = 2_000        # per tree listing
    agent_max_task_description_chars: int = 4_000
    agent_planner_max_attempts: int = 3        # JSON-repair retries

    @property
    def cors_origin_list(self) -> list[str]:
        """Parse the comma-separated CORS origins into a clean list."""
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance.

    `lru_cache` means the environment is read exactly once per process,
    and tests can call `get_settings.cache_clear()` to reload.
    """
    return Settings()
