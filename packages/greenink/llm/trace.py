"""`llm_calls`: the Model Trace, the exact-repeat cache and the spend counters for budgets."""

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Protocol
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from greenink.core.enums import LLMCallStatus
from greenink.core.models import LLMCall
from greenink.db.models import LLMCallRow


class TraceStore(Protocol):
    async def record(
        self, call: LLMCall, output: dict[str, Any] | None, error: str | None = None
    ) -> None: ...

    async def find_cached(self, prompt_hash: str) -> dict[str, Any] | None:
        """Output of the latest successful call with this prompt hash."""
        ...

    async def spent_today_usd(self) -> float:
        """Spend since 00:00 UTC, for the daily cap."""
        ...

    async def spent_for_analysis_usd(self, analysis_id: UUID) -> float: ...


def _start_of_day() -> datetime:
    return datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)


class InMemoryTraceStore:
    """For tests, scripts and the eval harness."""

    def __init__(self) -> None:
        self.calls: list[tuple[LLMCall, dict[str, Any] | None, str | None]] = []

    async def record(self, call: LLMCall, output: dict[str, Any] | None, error: str | None = None) -> None:
        self.calls.append((call, output, error))

    async def find_cached(self, prompt_hash: str) -> dict[str, Any] | None:
        for call, output, _error in reversed(self.calls):
            if call.prompt_hash == prompt_hash and call.status == LLMCallStatus.OK and output is not None:
                found: dict[str, Any] = output
                return found
        return None

    async def spent_today_usd(self) -> float:
        start = _start_of_day()
        return sum(call.cost_usd for call, _, _ in self.calls if call.created_at >= start)

    async def spent_for_analysis_usd(self, analysis_id: UUID) -> float:
        return sum(call.cost_usd for call, _, _ in self.calls if call.analysis_id == analysis_id)


class SqlTraceStore:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def record(self, call: LLMCall, output: dict[str, Any] | None, error: str | None = None) -> None:
        async with self._sessions.begin() as session:
            session.add(
                LLMCallRow(
                    id=call.id,
                    analysis_id=call.analysis_id,
                    task=call.task,
                    model=call.model,
                    tokens_in=call.tokens_in,
                    tokens_out=call.tokens_out,
                    cost_usd=Decimal(str(call.cost_usd)),
                    latency_ms=call.latency_ms,
                    status=call.status,
                    prompt_hash=call.prompt_hash,
                    output=output,
                    error=error,
                    created_at=call.created_at,
                )
            )

    async def find_cached(self, prompt_hash: str) -> dict[str, Any] | None:
        query = (
            select(LLMCallRow.output)
            .where(
                LLMCallRow.prompt_hash == prompt_hash,
                LLMCallRow.status == LLMCallStatus.OK,
                LLMCallRow.output.is_not(None),
            )
            .order_by(LLMCallRow.created_at.desc())
            .limit(1)
        )
        async with self._sessions() as session:
            output: dict[str, Any] | None = (await session.execute(query)).scalar_one_or_none()
            return output

    async def spent_today_usd(self) -> float:
        query = select(func.coalesce(func.sum(LLMCallRow.cost_usd), 0)).where(
            LLMCallRow.created_at >= _start_of_day()
        )
        async with self._sessions() as session:
            return float((await session.execute(query)).scalar_one())

    async def spent_for_analysis_usd(self, analysis_id: UUID) -> float:
        query = select(func.coalesce(func.sum(LLMCallRow.cost_usd), 0)).where(
            LLMCallRow.analysis_id == analysis_id
        )
        async with self._sessions() as session:
            return float((await session.execute(query)).scalar_one())
