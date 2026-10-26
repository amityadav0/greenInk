"""Check Token Factory access for every model in `config/models.yaml`.

Lists the account's Nemotron model IDs (GET /v1/models), then sends a 5-token chat call to
every configured model (primary, fallback and priced). Prints OK or the error for each and
exits non-zero on any failure.

    make check-models     # reads NEBIUS_API_KEY from .env
"""

import os
import sys

from pydantic import SecretStr

from greenink.core.settings import get_settings
from greenink.llm.probe import ProbeError, list_models, make_client, ping
from greenink.llm.router import load_models_config


def main() -> int:
    config = load_models_config(get_settings().config_dir / "models.yaml")
    key_env = config.provider.api_key_env
    api_key = os.environ.get(key_env)
    if not api_key:
        print(f"FAIL {key_env} is not set. Put it in .env (see .env.example).")
        return 2

    client = make_client(config, SecretStr(api_key))
    print(f"Provider: {config.provider.base_url}")
    try:
        available = list_models(client)
    except ProbeError as exc:
        print(f"FAIL {exc}")
        return 1

    nemotron = [model for model in available if "nemotron" in model.lower()]
    print(f"Account models: {len(available)} total, {len(nemotron)} Nemotron")
    for model in nemotron:
        print(f"  {model}")

    configured = sorted(config.models() | set(config.pricing_usd_per_1m))
    print(f"\nPinging {len(configured)} configured models:")
    failures = 0
    for model in configured:
        result = ping(client, model)
        listed = "" if model in available else " [not listed by /v1/models]"
        status = "OK  " if result.ok else "FAIL"
        failures += not result.ok
        print(f"{status} {model}{listed}: {result.detail}")

    print(f"\n{len(configured) - failures}/{len(configured)} configured models OK")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
