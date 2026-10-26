"""JSON Schemas for every contract model, as written to `contracts/schemas/`."""

import json

from pydantic import BaseModel

from greenink.core import api, models


def contract_models() -> list[type[BaseModel]]:
    """Every public `Contract` model defined in `core.models` and `core.api`, by name."""
    found: dict[str, type[BaseModel]] = {}
    for module in (models, api):
        for name, value in vars(module).items():
            if (
                isinstance(value, type)
                and issubclass(value, models.Contract)
                and value is not models.Contract
                and value.__module__ == module.__name__
            ):
                found[name] = value
    return [found[name] for name in sorted(found)]


def render_schemas() -> dict[str, str]:
    """File name -> JSON text, for every contract model."""
    return {
        f"{model.__name__}.json": json.dumps(model.model_json_schema(), indent=2, sort_keys=True) + "\n"
        for model in contract_models()
    }
