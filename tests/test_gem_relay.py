"""RelayTransport: GeM traffic through the Mumbai relay behaves like a direct connection."""

import asyncio
import json

import httpx
import pytest

from greenink.core.enums import ErrorCode
from greenink.core.errors import GreenInkError
from greenink.sources.config import load_sources_config
from greenink.sources.gem import GemBidplusAdapter, RateLimiter, RelayTransport
from tests.conftest import REPO_ROOT

RELAY = "https://relay.example/api/relay"
GEM = load_sources_config(REPO_ROOT / "config" / "sources.yaml").adapters.gem


def relay_handler(seen: list[httpx.Request]):  # type: ignore[no-untyped-def]
    def handle(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        assert str(request.url) == RELAY
        if request.headers.get("x-relay-key") != "k":
            return httpx.Response(401, content=b"unauthorised")
        target = request.headers["x-target-url"]
        if target.endswith("/old"):
            return httpx.Response(302, headers={"location": "https://bidplus.gem.gov.in/all-bids"})
        if target.endswith("/all-bids"):
            assert "x-relay-key" in request.headers
            return httpx.Response(
                200,
                headers={"set-cookie": "ci_session=abc; Path=/; Domain=bidplus.gem.gov.in"},
                text="data: {'payload': x, 'csrf_bd_gem_nk': '0123abcd'},",
            )
        if target.endswith("/all-bids-data"):
            assert request.headers.get("cookie") == "ci_session=abc", "session cookie travels back"
            body = {
                "code": 200,
                "response": {
                    "response": {
                        "numFound": 1,
                        "docs": [
                            {
                                "b_id": [7],
                                "b_bid_number": ["GEM/2026/B/7"],
                                "b_category_name": ["11kV Current Transformer"],
                            }
                        ],
                    }
                },
            }
            return httpx.Response(200, json=body)
        return httpx.Response(404)

    return handle


def client(key: str, seen: list[httpx.Request]) -> httpx.AsyncClient:
    transport = RelayTransport(RELAY, key, inner=httpx.MockTransport(relay_handler(seen)))
    return httpx.AsyncClient(transport=transport, follow_redirects=True)


def test_cookies_and_redirects_work_through_the_relay() -> None:
    async def scenario() -> None:
        seen: list[httpx.Request] = []
        async with client("k", seen) as c:
            first = await c.get("https://bidplus.gem.gov.in/old")
            assert first.status_code == 200
            assert str(first.url) == "https://bidplus.gem.gov.in/all-bids"
            assert c.cookies.get("ci_session") == "abc", "GeM's session cookie is kept for GeM"
            data = await c.post("https://bidplus.gem.gov.in/all-bids-data", data={"payload": "{}"})
            assert data.json()["code"] == 200
        assert [r.headers["x-target-url"] for r in seen] == [
            "https://bidplus.gem.gov.in/old",
            "https://bidplus.gem.gov.in/all-bids",
            "https://bidplus.gem.gov.in/all-bids-data",
        ]

    asyncio.run(scenario())


def test_adapter_searches_through_the_relay() -> None:
    async def scenario() -> None:
        seen: list[httpx.Request] = []
        transport = RelayTransport(RELAY, "k", inner=httpx.MockTransport(relay_handler(seen)))

        async def no_sleep(_: float) -> None:
            return None

        adapter = GemBidplusAdapter(GEM, RateLimiter(1000), transport=transport, sleep=no_sleep)
        try:
            [tender] = await adapter.search("current transformer")
        finally:
            await adapter.aclose()
        assert tender.source_ref == "GEM/2026/B/7"
        assert (
            json.loads(
                seen[-1]
                .content.decode()
                .split("payload=")[1]
                .split("&")[0]
                .replace("%22", '"')
                .replace("%3A", ":")
                .replace("%2C", ",")
                .replace("%7B", "{")
                .replace("%7D", "}")
                .replace("+", " ")
                or "{}"
            )["param"]["searchBid"]
            == "current transformer"
        )

    asyncio.run(scenario())


def test_wrong_key_is_a_clean_upstream_error() -> None:
    async def scenario() -> None:
        transport = RelayTransport(RELAY, "wrong", inner=httpx.MockTransport(relay_handler([])))

        async def no_sleep(_: float) -> None:
            return None

        adapter = GemBidplusAdapter(GEM, RateLimiter(1000), transport=transport, sleep=no_sleep)
        try:
            with pytest.raises(GreenInkError) as caught:
                await adapter.search("current transformer")
        finally:
            await adapter.aclose()
        assert caught.value.code == ErrorCode.UPSTREAM_UNAVAILABLE

    asyncio.run(scenario())
