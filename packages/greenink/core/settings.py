"""Runtime settings, read from environment variables (see `.env.example`).

Secrets are `SecretStr` so they never appear in reprs or logs.
"""

import os
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, ConfigDict, SecretStr, field_validator

_REPO_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseModel):
    model_config = ConfigDict(frozen=True)

    env: str = "local"
    log_level: str = "INFO"
    config_dir: Path = _REPO_ROOT / "config"

    database_url: str = "postgresql+psycopg://greenink:greenink@localhost:5433/greenink"
    redis_url: str = "redis://localhost:6380/0"

    nebius_api_key: SecretStr | None = None
    tavily_api_key: SecretStr | None = None

    r2_endpoint_url: str = "http://localhost:9000"
    r2_access_key_id: SecretStr | None = None
    r2_secret_access_key: SecretStr | None = None
    r2_bucket: str = "greenink"
    r2_addressing_style: str = "path"
    """`path` for MinIO; `virtual` for Railway buckets and most hosted S3."""

    session_secret: SecretStr | None = None
    gem_proxy_url: SecretStr | None = None
    """HTTP(S) proxy for GeM traffic only, e.g. http://user:pass@in-host:3128 (GeM blocks many
    non-Indian IPs). Secret because it carries credentials."""
    rate_limit_exempt_token: SecretStr | None = None
    """Operators (pre-warm script) send it as X-Greenink-Admin to skip per-IP limits."""
    web_origin: str = "http://localhost:3000"

    @field_validator("database_url")
    @classmethod
    def _psycopg_driver(cls, value: str) -> str:
        """Hosted Postgres (Railway, Neon) hands out postgres:// URLs; SQLAlchemy needs the driver."""
        for prefix in ("postgres://", "postgresql://"):
            if value.startswith(prefix):
                return "postgresql+psycopg://" + value.removeprefix(prefix)
        return value

    @classmethod
    def from_env(cls) -> "Settings":
        """Each field reads the env var of the same name in upper case, e.g. `DATABASE_URL`."""
        values = {name: os.environ[name.upper()] for name in cls.model_fields if os.environ.get(name.upper())}
        return cls.model_validate(values)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings.from_env()
