"""Routing table: `config/models.yaml` parsed into typed config.

Model IDs and prices live only in that file; this module is the only reader.
"""

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator

from greenink.core.enums import LLMTask

DEFAULT_CONCURRENCY = 4


class _Config(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ProviderConfig(_Config):
    base_url: HttpUrl
    api_key_env: str


class TaskRoute(_Config):
    model: str
    fallback: str | None = None
    timeout_s: float = Field(gt=0)
    max_concurrency: int | None = Field(default=None, ge=1)
    thinking: bool = Field(default=False, description="Nemotron reasoning; reasoning tokens bill as output.")
    max_output_tokens: int = Field(default=2048, ge=16, description="Hard cap per call, reasoning included.")


class ModelPrice(_Config):
    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)

    input: float = Field(alias="in", ge=0, description="USD per 1M input tokens.")
    output: float = Field(alias="out", ge=0, description="USD per 1M output tokens.")


class Budgets(_Config):
    per_analysis_usd: float = Field(gt=0)
    daily_usd: float = Field(gt=0)


class ModelsConfig(_Config):
    provider: ProviderConfig
    tasks: dict[LLMTask, TaskRoute]
    pricing_usd_per_1m: dict[str, ModelPrice]
    budgets: Budgets

    @model_validator(mode="after")
    def _every_task_routed_and_priced(self) -> "ModelsConfig":
        missing_tasks = set(LLMTask) - set(self.tasks)
        if missing_tasks:
            raise ValueError(f"tasks missing from models.yaml: {sorted(missing_tasks)}")
        unpriced = self.models() - set(self.pricing_usd_per_1m)
        if unpriced:
            raise ValueError(f"models without a price in models.yaml: {sorted(unpriced)}")
        return self

    def models(self) -> set[str]:
        """Every model a task can reach, primary or fallback."""
        routed = {route.model for route in self.tasks.values()}
        fallbacks = {route.fallback for route in self.tasks.values() if route.fallback}
        return routed | fallbacks

    def route(self, task: LLMTask) -> TaskRoute:
        return self.tasks[task]

    def concurrency(self, model: str) -> int:
        """Per-model limit: the smallest `max_concurrency` among tasks routed to `model`."""
        limits = [
            route.max_concurrency
            for route in self.tasks.values()
            if route.max_concurrency and model in (route.model, route.fallback)
        ]
        return min(limits, default=DEFAULT_CONCURRENCY)


def load_models_config(path: Path) -> ModelsConfig:
    with path.open(encoding="utf-8") as f:
        return ModelsConfig.model_validate(yaml.safe_load(f))
