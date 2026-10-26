"""Worker lifecycle against a real Redis (`docker compose up redis`); skipped when unreachable."""

import asyncio

import pytest
from arq.connections import RedisSettings, create_pool

from greenink.core.settings import Settings, get_settings
from greenink.jobs.queue import QueueName
from greenink_worker.__main__ import run

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


def test_worker_runs_all_queues_executes_jobs_and_stops_cleanly(settings: Settings) -> None:
    async def scenario() -> None:
        stop = asyncio.Event()
        worker = asyncio.create_task(run(list(QueueName), settings, stop))
        pool = await create_pool(RedisSettings.from_dsn(settings.redis_url))
        try:
            job = await pool.enqueue_job(
                "judge", "analysis-1", {}, _queue_name="q.judge", _job_id="judge:analysis-1"
            )
            assert job is not None
            # Same idempotency key: arq refuses a second job, so the stage runs once.
            duplicate = await pool.enqueue_job(
                "judge", "analysis-1", {}, _queue_name="q.judge", _job_id="judge:analysis-1"
            )
            assert duplicate is None
            # The stub handler raises NotImplementedError: proves queue -> function wiring.
            with pytest.raises(NotImplementedError, match="lane-A"):
                await job.result(timeout=15)
        finally:
            stop.set()
            await asyncio.wait_for(worker, timeout=15)
            await pool.flushdb()
            await pool.aclose()

    asyncio.run(scenario())


def test_worker_fails_loudly_when_redis_is_unreachable() -> None:
    settings = Settings(redis_url="redis://127.0.0.1:1/0")

    async def scenario() -> None:
        await asyncio.wait_for(run([QueueName.TRIAGE], settings), timeout=30)

    with pytest.raises(Exception, match=r"(?i)connect|refused|redis"):
        asyncio.run(scenario())
