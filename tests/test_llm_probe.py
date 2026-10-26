"""Token Factory probe with a mocked transport: no network, no key."""

import json

import httpx2
import pytest
from pydantic import SecretStr

from greenink.llm.probe import PING_MAX_TOKENS, ProbeError, list_models, make_client, ping
from greenink.llm.router import load_models_config
from tests.conftest import REPO_ROOT

CONFIG = load_models_config(REPO_ROOT / "config" / "models.yaml")


def client_with(handler: httpx2.MockTransport) -> object:
    return make_client(CONFIG, SecretStr("test-key"), http_client=httpx2.Client(transport=handler))


def test_list_models_and_ping_ok() -> None:
    seen: list[dict[str, object]] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        assert request.headers["authorization"] == "Bearer test-key"
        assert str(request.url).startswith("https://api.tokenfactory.nebius.com/v1/")
        if request.url.path.endswith("/models"):
            return httpx2.Response(
                200,
                json={
                    "object": "list",
                    "data": [
                        {"id": "vendor/model-b", "object": "model", "created": 0, "owned_by": "x"},
                        {"id": "vendor/model-a", "object": "model", "created": 0, "owned_by": "x"},
                    ],
                },
            )
        body = json.loads(request.content)
        seen.append(body)
        return httpx2.Response(
            200,
            json={
                "id": "c1",
                "object": "chat.completion",
                "created": 0,
                "model": body["model"],
                "choices": [
                    {"index": 0, "finish_reason": "length", "message": {"role": "assistant", "content": "OK"}}
                ],
                "usage": {"prompt_tokens": 12, "completion_tokens": 1, "total_tokens": 13},
            },
        )

    client = client_with(httpx2.MockTransport(handler))
    assert list_models(client) == ["vendor/model-a", "vendor/model-b"]  # type: ignore[arg-type]
    result = ping(client, "vendor/model-a")  # type: ignore[arg-type]
    assert result.ok
    assert "12 in / 1 out" in result.detail
    assert seen[0]["max_tokens"] == PING_MAX_TOKENS


def test_ping_reports_http_error_without_raising() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(404, json={"error": {"message": "model not found"}})

    result = ping(client_with(httpx2.MockTransport(handler)), "vendor/missing")  # type: ignore[arg-type]
    assert not result.ok
    assert result.detail.startswith("HTTP 404")
    assert "test-key" not in result.detail


def test_list_models_auth_error_is_a_probe_error() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(401, json={"error": {"message": "invalid api key"}})

    with pytest.raises(ProbeError, match="HTTP 401"):
        list_models(client_with(httpx2.MockTransport(handler)))  # type: ignore[arg-type]
