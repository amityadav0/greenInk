"""A user's journey through the HTTP API, with the real worker running in a background thread.

Real Postgres, Redis, queues and SSE; fake LLM and fake GeM, so no credits.
"""

import asyncio
import json
import threading
from collections.abc import Iterator
from typing import Any

import pytest
from arq.connections import ArqRedis
from fastapi.testclient import TestClient
from pydantic import SecretStr

from greenink.core.enums import ErrorCode
from greenink.core.errors import GreenInkError
from greenink.core.settings import Settings, get_settings
from greenink.db.seed import DEMO_COMPANY_ID, seed_demo
from greenink.db.session import make_engine, make_sessionmaker
from greenink.jobs.events import RedisEventBus
from greenink.jobs.queue import ArqJobQueue, QueueName
from greenink.sources.config import load_sources_config
from greenink.storage.blob import MemoryBlobStore
from greenink_api.deps import AppState
from greenink_api.main import create_app
from greenink_worker.__main__ import run
from tests.conftest import REPO_ROOT
from tests.integration import FakeGem, bid_pdf, make_services, migrate

pytestmark = [pytest.mark.db, pytest.mark.redis]

REDIS_TEST_DB = 12


class WorkerThread:
    """The worker on its own event loop, as in production (a separate process)."""

    def __init__(self, database_url: str, redis_url: str, blobs: MemoryBlobStore) -> None:
        self._args = (database_url, redis_url, blobs)
        self._ready = threading.Event()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._stop: asyncio.Event | None = None
        self._thread = threading.Thread(target=self._main, daemon=True)

    def _main(self) -> None:
        async def body() -> None:
            services = await make_services(*self._args[:2], blobs=self._args[2])
            self._loop = asyncio.get_running_loop()
            self._stop = asyncio.Event()
            self._ready.set()
            try:
                await run(list(QueueName), services.settings, self._stop, services)
            finally:
                await services.aclose()

        asyncio.run(body())

    def __enter__(self) -> "WorkerThread":
        self._thread.start()
        assert self._ready.wait(10)
        return self

    def __exit__(self, *_: object) -> None:
        assert self._loop is not None
        assert self._stop is not None
        self._loop.call_soon_threadsafe(self._stop.set)
        self._thread.join(15)


@pytest.fixture
def env(scratch_database_url: str) -> Iterator[tuple[TestClient, MemoryBlobStore]]:
    migrate(scratch_database_url)
    redis_url = get_settings().redis_url.rsplit("/", 1)[0] + f"/{REDIS_TEST_DB}"
    settings = Settings(database_url=scratch_database_url, redis_url=redis_url)
    blobs = MemoryBlobStore()

    async def prepare() -> None:
        engine = make_engine(scratch_database_url)
        await seed_demo(make_sessionmaker(engine))
        await engine.dispose()
        redis = ArqRedis.from_url(redis_url)
        await redis.flushdb()
        await redis.aclose()

    asyncio.run(prepare())

    async def state_factory(s: Settings) -> AppState:
        engine = make_engine(s.database_url)
        redis = ArqRedis.from_url(s.redis_url)
        return AppState(
            settings=s,
            engine=engine,
            sessions=make_sessionmaker(engine),
            redis=redis,
            queue=ArqJobQueue(redis),
            events=RedisEventBus(make_sessionmaker(engine), redis),
            blobs=blobs,
            gem=FakeGem(),
            sources=load_sources_config(REPO_ROOT / "config" / "sources.yaml"),
        )

    with (
        WorkerThread(scratch_database_url, redis_url, blobs),
        TestClient(create_app(settings, state_factory), raise_server_exceptions=False) as client,
    ):
        yield client, blobs


def sse(client: TestClient, url: str) -> list[tuple[str, dict[str, Any]]]:
    events: list[tuple[str, dict[str, Any]]] = []
    name = "message"
    with client.stream("GET", url, timeout=60) as response:
        assert response.status_code == 200
        for line in response.iter_lines():
            if line.startswith("event:"):
                name = line.split(":", 1)[1].strip()
            elif line.startswith("data:"):
                events.append((name, json.loads(line.split(":", 1)[1])))
                if name == "done":
                    break
                name = "message"
    return events


def test_search_open_report_and_fix(env: tuple[TestClient, MemoryBlobStore]) -> None:
    client, _ = env

    companies = client.get("/v1/companies")
    assert companies.status_code == 200
    assert "gi_session" in client.cookies
    [demo] = companies.json()
    assert demo["id"] == str(DEMO_COMPANY_ID)
    assert demo["read_only"] is True

    search = client.get("/v1/search", params={"q": "Current  Transformer"})
    assert search.status_code == 200, search.text
    body = search.json()
    assert body["query"] == "current transformer"
    assert body["cached"] is False
    [bid] = body["results"]
    badges = sse(client, body["events_url"])
    assert (
        "badge",
        {
            "search_id": body["search_id"],
            "source_ref": bid["source_ref"],
            "badge": {"level": "green", "reason": "Makes CTs."},
        },
    ) in badges
    again = client.get("/v1/search", params={"q": "current transformer"}).json()
    assert again["cached"] is True
    assert again["results"][0]["badge"]["level"] == "green"

    started = client.post(
        "/v1/analyses", json={"tender_id": bid["tender_id"], "company_id": str(DEMO_COMPANY_ID)}
    )
    assert started.status_code == 202, started.text
    accepted = started.json()
    assert accepted["cached"] is False
    events = sse(client, accepted["events_url"])
    stages = [(e["stage"], e["state"]) for name, e in events if name == "stage"]
    assert ("verdict", "done") in stages
    assert ("intel", "done") in stages

    report = client.get(accepted["status_url"]).json()
    assert report["analysis"]["verdict"] == "skip"
    first = report["findings"][0]
    assert first["status"] == "fail"
    assert first["requirement"]["page_no"] == 2
    assert report["price_intel"][0]["sources"][0]["url"] == "https://example.invalid/award"

    tender = client.get(f"/v1/tenders/{bid['tender_id']}").json()
    [document] = tender["documents"]
    pdf = client.get(document["download_url"])
    assert pdf.status_code == 200
    assert pdf.content == bid_pdf() or pdf.content.startswith(b"%PDF")
    page = client.get(f"/v1/tenders/{bid['tender_id']}/pages/2").json()
    assert "BIS licence" in page["text"]

    trace = client.get(f"{accepted['status_url']}/trace").json()
    assert trace["totals"]["tokens_in"] >= 0
    assert {c["task"] for c in trace["calls"]} >= set()

    fix_url = f"{accepted['status_url']}/findings/{first['id']}/fix"
    assert client.post(fix_url).status_code == 202
    for _ in range(100):
        response = client.post(fix_url)
        if response.status_code == 200:
            break
        threading.Event().wait(0.1)
    assert response.status_code == 200
    assert response.json()["title"] == "Plan the BIS licence"

    cached = client.post(
        "/v1/analyses", json={"tender_id": bid["tender_id"], "company_id": str(DEMO_COMPANY_ID)}
    )
    assert cached.json() == {**accepted, "cached": True}


def test_upload_companies_and_privacy(env: tuple[TestClient, MemoryBlobStore]) -> None:
    client, blobs = env

    upload = client.post(
        "/v1/tenders/upload", files={"file": ("state-bid.pdf", bid_pdf(), "application/pdf")}
    )
    assert upload.status_code == 202, upload.text
    tender = client.get(upload.json()["status_url"]).json()
    assert tender["tender"]["source"] == "upload"
    assert tender["documents"][0]["filename"] == "state-bid.pdf"

    rejected = client.post(
        "/v1/tenders/upload", files={"file": ("x.pdf", b"<html>not a pdf</html>", "application/pdf")}
    )
    assert rejected.status_code == 415
    assert rejected.json()["code"] == "unsupported_media_type"

    created = client.post(
        "/v1/companies", json={"name": "Example Works", "profile": {"legal_name": "Example Works"}}
    )
    assert created.status_code == 201
    mine = created.json()
    assert [c["id"] for c in client.get("/v1/companies").json()] == [str(DEMO_COMPANY_ID), mine["id"]]

    # Same running app, separate cookie jar: another visitor. (No `with`: that would rerun startup.)
    stranger = TestClient(client.app)
    assert [c["id"] for c in stranger.get("/v1/companies").json()] == [str(DEMO_COMPANY_ID)]
    hidden = stranger.post(
        "/v1/analyses", json={"tender_id": tender["tender"]["id"], "company_id": mine["id"]}
    )
    assert hidden.status_code == 404

    demo_doc = client.post(
        f"/v1/companies/{DEMO_COMPANY_ID}/documents", files={"file": ("a.pdf", bid_pdf(), "application/pdf")}
    )
    assert demo_doc.status_code == 400

    doc = client.post(
        f"/v1/companies/{mine['id']}/documents",
        files={"file": ("udyam.pdf", bid_pdf(), "application/pdf")},
        data={"kind": "udyam_certificate"},
    )
    assert doc.status_code == 202, doc.text
    assert any(key.startswith(f"companies/{mine['id']}/") for key in blobs.blobs)


def test_new_reports_are_rate_limited_per_ip(env: tuple[TestClient, MemoryBlobStore]) -> None:
    client, _ = env
    headers = {"X-Forwarded-For": "203.0.113.9"}
    statuses = []
    for n in range(11):
        upload = client.post(
            "/v1/tenders/upload",
            files={"file": (f"bid-{n}.pdf", bid_pdf() + str(n).encode(), "application/pdf")},
            headers={"X-Forwarded-For": f"198.51.100.{n}"},
        )
        tender_id = upload.json()["id"]
        statuses.append(
            client.post(
                "/v1/analyses",
                json={"tender_id": tender_id, "company_id": str(DEMO_COMPANY_ID)},
                headers=headers,
            ).status_code
        )
    assert statuses[:10] == [202] * 10
    assert statuses[10] == 429


def test_finished_report_replays_every_stage(env: tuple[TestClient, MemoryBlobStore]) -> None:
    client, _ = env
    bid = client.get("/v1/search", params={"q": "current transformer"}).json()["results"][0]
    accepted = client.post(
        "/v1/analyses", json={"tender_id": bid["tender_id"], "company_id": str(DEMO_COMPANY_ID)}
    ).json()
    live = [e for name, e in sse(client, accepted["events_url"]) if name == "stage"]
    replay = [e for name, e in sse(client, accepted["events_url"]) if name == "stage"]

    # Live order is publish order; replay order is id order. The same events must arrive.
    def key(e: dict[str, Any]) -> tuple[str, str, str]:
        return (e["stage"], e["state"], e["message"])

    assert sorted(map(key, replay)) == sorted(map(key, live)), "a finished report replays everything"
    assert {"verdict", "intel", "extract"} <= {e["stage"] for e in replay}


def test_operator_token_skips_rate_limits(env: tuple[TestClient, MemoryBlobStore]) -> None:
    client, _ = env
    state = client.app.state.services  # type: ignore[attr-defined]
    state.settings = state.settings.model_copy(update={"rate_limit_exempt_token": SecretStr("op-token")})

    def new_reports(ip: str, token: str, count: int) -> list[int]:
        codes = []
        for n in range(count):
            pdf = bid_pdf() + f"{ip}-{n}".encode()
            upload = client.post(  # setup only: uploads use the operator token
                "/v1/tenders/upload",
                files={"file": (f"{n}.pdf", pdf, "application/pdf")},
                headers={"X-Greenink-Admin": "op-token"},
            )
            codes.append(
                client.post(
                    "/v1/analyses",
                    json={"tender_id": upload.json()["id"], "company_id": str(DEMO_COMPANY_ID)},
                    headers={"X-Forwarded-For": ip, "X-Greenink-Admin": token},
                ).status_code
            )
        return codes

    assert new_reports("203.0.113.77", "op-token", 12) == [202] * 12
    assert new_reports("203.0.113.78", "wrong", 11)[-1] == 429, "a wrong token gets the normal limit"


def test_search_falls_back_to_stored_bids_when_gem_is_unreachable(
    env: tuple[TestClient, MemoryBlobStore],
) -> None:
    client, _ = env
    first = client.get("/v1/search", params={"q": "current transformer"}).json()
    [stored] = first["results"]

    async def down(query: str) -> list[Any]:
        raise GreenInkError(ErrorCode.UPSTREAM_UNAVAILABLE, "GeM is not responding right now.")

    client.app.state.services.gem.search = down  # type: ignore[attr-defined]
    fallback = client.get("/v1/search", params={"q": "11kV transformer"})
    assert fallback.status_code == 200, fallback.text
    body = fallback.json()
    assert body["cached"] is True
    assert [r["tender_id"] for r in body["results"]] == [stored["tender_id"]]

    nothing = client.get("/v1/search", params={"q": "office chair"})
    assert nothing.status_code == 502
    assert nothing.json()["code"] == "upstream_unavailable"
