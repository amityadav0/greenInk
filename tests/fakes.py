"""Test doubles shared by pipeline tests."""

from collections.abc import Callable
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel

from greenink.core.enums import LLMTask
from greenink.llm.port import LLMInput, LLMResult

Responder = Callable[[LLMInput], BaseModel | dict[str, Any]]


class FakeLLM:
    """Answers each task from a responder; records every call. Implements the LLM port."""

    def __init__(self, **responders: Responder) -> None:
        self.responders = responders
        self.calls: list[tuple[LLMTask, LLMInput, UUID | None]] = []

    async def run[T: BaseModel](
        self, task: LLMTask, input: LLMInput, schema: type[T], *, analysis_id: UUID | None = None
    ) -> LLMResult[T]:
        self.calls.append((task, input, analysis_id))
        answer = self.responders[task.value](input)
        output = schema.model_validate(answer.model_dump() if isinstance(answer, BaseModel) else answer)
        return LLMResult(
            output=output,
            call_id=uuid4(),
            model="fake",
            tokens_in=1,
            tokens_out=1,
            cost_usd=0.0,
            latency_ms=1,
            cached=False,
        )
