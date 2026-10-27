"""Worker lifecycle against a real Redis (`docker compose up redis`); skipped when unreachable."""

import asyncio
from typing import cast
from uuid import uuid4

import pytest
from arq.connections import RedisSettings, create_pool

from greenink.core.settings import Settings, get_settings
from greenink.jobs.queue import ArqJobQueue, JobName, QueueName
from greenink_worker.__main__ import run
from greenink_worker.wiring import Services

pytestmark = pytest.mark.redis

TEST_DB = 15


@pytest.fixture
def settings() -> Settings:
    url = get_settings().redis_url.rsplit("/", 1)[0] + f"/{TEST_DB}"

    async def probe() -> None:
        redis_settings = RedisSettings.from_dsn(url)
        redis_settings.conn_retries = 0
        pool = await create_pool(redis_settings)
        await pool.flushdb()
        await pool.aclose()

    try:
        asyncio.run(probe())
    except Exception:
        pytest.skip("Redis unreachable at REDIS_URL")
    return Settings(redis_url=url)


def test_duplicate_keys_are_refused_only_while_queued(settings: Settings) -> None:
    async def scenario() -> None:
        pool = await create_pool(RedisSettings.from_dsn(settings.redis_url))
        try:
            queue = ArqJobQueue(pool)
            payload = {"search_id": "s", "company_id": str(uuid4()), "bids": []}
            assert await queue.enqueue(JobName.TRIAGE, "k", payload)
            assert not await queue.enqueue(JobName.TRIAGE, "k", payload), "same key while queued"
            assert await queue.enqueue(JobName.TRIAGE, "other", payload)
        finally:
            await pool.flushdb()
            await pool.aclose()

    asyncio.run(scenario())


def test_worker_fails_loudly_when_redis_is_unreachable() -> None:
    settings = Settings(redis_url="redis://127.0.0.1:1/0")

    async def scenario() -> None:
        await asyncio.wait_for(run([QueueName.TRIAGE], settings, services=_no_services()), timeout=30)

    with pytest.raises(Exception, match=r"(?i)connect|refused|redis"):
        asyncio.run(scenario())


def _no_services() -> Services:
    """The worker fails on Redis before it touches a service, so a stand-in is enough."""
    return cast(Services, object())
