"""config/models.yaml: every task routed, every reachable model priced."""

import re
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from greenink.core.enums import LLMTask
from greenink.llm.pricing import cost_usd
from greenink.llm.router import ModelPrice, ModelsConfig, load_models_config
from tests.conftest import REPO_ROOT

MODELS_YAML = REPO_ROOT / "config" / "models.yaml"


def test_models_yaml_loads_and_routes_every_task() -> None:
    config = load_models_config(MODELS_YAML)
    assert set(config.tasks) == set(LLMTask)
    assert str(config.provider.base_url) == "https://api.tokenfactory.nebius.com/v1/"
    assert config.provider.api_key_env == "NEBIUS_API_KEY"
    assert len(config.models()) == 4


def test_models_yaml_is_spec_verbatim() -> None:
    spec = (REPO_ROOT / "docs" / "SPEC.md").read_text(encoding="utf-8")
    block = re.search(r"```yaml\n(# config/models\.yaml.*?)```", spec, flags=re.DOTALL)
    assert block is not None
    assert MODELS_YAML.read_text(encoding="utf-8") == block.group(1)


def test_unpriced_model_is_rejected(tmp_path: Path) -> None:
    raw = yaml.safe_load(MODELS_YAML.read_text(encoding="utf-8"))
    raw["pricing_usd_per_1m"].pop(raw["tasks"]["judge"]["model"])
    with pytest.raises(ValidationError, match="without a price"):
        ModelsConfig.model_validate(raw)


def test_missing_task_is_rejected() -> None:
    raw = yaml.safe_load(MODELS_YAML.read_text(encoding="utf-8"))
    raw["tasks"].pop("fix")
    with pytest.raises(ValidationError, match="tasks missing"):
        ModelsConfig.model_validate(raw)


def test_cost_usd() -> None:
    price = ModelPrice.model_validate({"in": 0.30, "out": 0.90})
    assert cost_usd(price, 40_000, 2_000) == pytest.approx(0.0138)


def test_no_model_ids_outside_config() -> None:
    """AGENTS rule 2: model IDs live only in config/models.yaml."""
    offenders = [
        str(path.relative_to(REPO_ROOT))
        for root in ("packages", "apps/api", "apps/worker", "scripts")
        for path in (REPO_ROOT / root).rglob("*.py")
        if re.search(r"nvidia/", path.read_text(encoding="utf-8"), flags=re.IGNORECASE)
    ]
    assert offenders == []
