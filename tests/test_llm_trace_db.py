"""SqlTraceStore against a migrated scratch Postgres (`docker compose up postgres`)."""

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config

from greenink.core.enums import LLMCallStatus, LLMTask
from greenink.core.models import LLMCall
from greenink.db.session import make_engine, make_sessionmaker
from greenink.llm.trace import SqlTraceStore
from tests.conftest import REPO_ROOT

pytestmark = pytest.mark.db


def _call(cost: float, status: LLMCallStatus, prompt_hash: str, at: datetime) -> LLMCall:
    return LLMCall(
        id=uuid4(),
        task=LLMTask.EXTRACT,
        model="vendor/model",
        tokens_in=10,
        tokens_out=5,
        cost_usd=cost,
        latency_ms=12,
        status=status,
        prompt_hash=prompt_hash,
        created_at=at,
    )


def test_record_cache_lookup_and_daily_spend(
    scratch_database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATABASE_URL", scratch_database_url)
    command.upgrade(Config(str(REPO_ROOT / "packages" / "greenink" / "db" / "alembic.ini")), "head")

    async def scenario() -> None:
        engine = make_engine(scratch_database_url)
        store = SqlTraceStore(make_sessionmaker(engine))
        now = datetime.now(UTC)
        key = "a" * 64
        try:
            await store.record(_call(0.01, LLMCallStatus.OK, key, now - timedelta(minutes=5)), {"v": 1})
            await store.record(_call(0.02, LLMCallStatus.OK, key, now), {"v": 2})
            await store.record(_call(0.0, LLMCallStatus.ERROR, key, now), None, "boom")
            await store.record(_call(0.5, LLMCallStatus.OK, "b" * 64, now - timedelta(days=2)), {"v": 9})

            assert await store.find_cached(key) == {"v": 2}
            assert await store.find_cached("c" * 64) is None
            assert await store.spent_today_usd() == pytest.approx(0.03)
            assert await store.spent_for_analysis_usd(uuid4()) == 0
        finally:
            await engine.dispose()

    asyncio.run(scenario())
