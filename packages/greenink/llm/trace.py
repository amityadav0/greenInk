"""Writes and reads `llm_calls`: the Model Trace and the exact-repeat cache."""

from greenink.core.models import LLMCall


class TraceStore:
    async def record(self, call: LLMCall) -> None:
        raise NotImplementedError("TODO(lane-A): insert into llm_calls")

    async def find_cached(self, prompt_hash: str) -> LLMCall | None:
        raise NotImplementedError("TODO(lane-A): prompt_hash lookup in llm_calls")

    async def spent_today_usd(self) -> float:
        raise NotImplementedError("TODO(lane-A): sum cost_usd for the daily budget")
