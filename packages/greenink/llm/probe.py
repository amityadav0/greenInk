"""Connectivity probe for Token Factory, used by `scripts/check_models.py`.

Lists the account's models and sends a tiny chat call to every configured model.
"""

from dataclasses import dataclass

import httpx2
import openai
from openai import OpenAI
from pydantic import SecretStr

from greenink.llm.router import ModelsConfig

PING_MAX_TOKENS = 5


class ProbeError(Exception):
    """Token Factory could not be reached or refused the request."""


@dataclass(frozen=True)
class ProbeResult:
    model: str
    ok: bool
    detail: str


def make_client(
    config: ModelsConfig, api_key: SecretStr, *, http_client: httpx2.Client | None = None
) -> OpenAI:
    return OpenAI(
        base_url=str(config.provider.base_url),
        api_key=api_key.get_secret_value(),
        max_retries=0,
        timeout=60,
        http_client=http_client,
    )


def list_models(client: OpenAI) -> list[str]:
    """All model IDs the account can call, sorted."""
    try:
        return sorted(model.id for model in client.models.list())
    except openai.APIStatusError as exc:
        raise ProbeError(f"GET /models: HTTP {exc.status_code}: {_short(exc.message)}") from None
    except openai.APIError as exc:
        raise ProbeError(f"GET /models: {type(exc).__name__}: {_short(exc.message)}") from None


def ping(client: OpenAI, model: str) -> ProbeResult:
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": "Reply with the single word OK."}],
            max_tokens=PING_MAX_TOKENS,
        )
    except openai.APIStatusError as exc:
        return ProbeResult(model, False, f"HTTP {exc.status_code}: {_short(exc.message)}")
    except openai.APIError as exc:
        return ProbeResult(model, False, f"{type(exc).__name__}: {_short(exc.message)}")
    usage = response.usage
    tokens = f"{usage.prompt_tokens} in / {usage.completion_tokens} out" if usage else "no usage"
    return ProbeResult(model, True, f"answered as {response.model} ({tokens})")


def _short(text: str, limit: int = 300) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1] + "…"
