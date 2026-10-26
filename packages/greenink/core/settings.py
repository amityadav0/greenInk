"""Runtime settings, read from environment variables (see `.env.example`).

Secrets are `SecretStr` so they never appear in reprs or logs.
"""

import os
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, ConfigDict, SecretStr

_REPO_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseModel):
    model_config = ConfigDict(frozen=True)

    env: str = "local"
    log_level: str = "INFO"
    config_dir: Path = _REPO_ROOT / "config"

    database_url: str = "postgresql+psycopg://greenink:greenink@localhost:5432/greenink"
    redis_url: str = "redis://localhost:6379/0"

    nebius_api_key: SecretStr | None = None
    tavily_api_key: SecretStr | None = None

    r2_endpoint_url: str = "http://localhost:9000"
    r2_access_key_id: SecretStr | None = None
    r2_secret_access_key: SecretStr | None = None
    r2_bucket: str = "greenink"

    session_secret: SecretStr | None = None
    web_origin: str = "http://localhost:3000"

    @classmethod
    def from_env(cls) -> "Settings":
        """Each field reads the env var of the same name in upper case, e.g. `DATABASE_URL`."""
        values = {name: os.environ[name.upper()] for name in cls.model_fields if os.environ.get(name.upper())}
        return cls.model_validate(values)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings.from_env()
