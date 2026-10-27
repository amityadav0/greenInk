"""`config/sources.yaml` parsed into typed config. Read only by `greenink.sources`."""

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class _Config(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class GemConfig(_Config):
    enabled: bool
    base_url: HttpUrl
    rate_limit_rps: float = Field(gt=0)
    timeout_s: float = Field(gt=0)
    max_retries: int = Field(ge=0)
    user_agent: str
    search_cache_ttl_s: int = Field(gt=0)
    max_results: int = Field(gt=0)


class UploadConfig(_Config):
    enabled: bool
    max_bytes: int = Field(gt=0)
    allowed_types: list[str]


class DisabledConfig(_Config):
    enabled: bool = False


class Adapters(_Config):
    gem: GemConfig
    upload: UploadConfig
    cppp: DisabledConfig


class SourcesConfig(_Config):
    adapters: Adapters


def load_sources_config(path: Path) -> SourcesConfig:
    with path.open(encoding="utf-8") as f:
        return SourcesConfig.model_validate(yaml.safe_load(f))
