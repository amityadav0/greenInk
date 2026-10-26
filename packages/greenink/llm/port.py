"""Port of the `llm` module: the only way any code calls a model."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Protocol
from uuid import UUID

from pydantic import BaseModel

from greenink.core.enums import LLMTask


@dataclass(frozen=True)
class LLMInput:
    """What a task sends to a model.

    `instructions` is trusted text (a rendered prompt from `analysis/prompts/`).
    `data` holds untrusted text, such as tender pages or website text, keyed by a short
    label; the gateway wraps each value in a delimited block and tells the model
    it is content to analyse, never instructions to follow.
    """

    instructions: str
    data: Mapping[str, str] = field(default_factory=dict)
    images: Sequence[bytes] = ()


@dataclass(frozen=True)
class LLMResult[T: BaseModel]:
    output: T
    call_id: UUID
    model: str
    """The model that actually answered, after any fallback."""
    tokens_in: int
    tokens_out: int
    cost_usd: float
    latency_ms: int
    cached: bool


class LLM(Protocol):
    async def run[T: BaseModel](
        self,
        task: LLMTask,
        input: LLMInput,
        schema: type[T],
        *,
        analysis_id: UUID | None = None,
    ) -> LLMResult[T]:
        """Route `task` to its model, validate the output against `schema`, record the call.

        Raises `GreenInkError(BUDGET_EXCEEDED)` when the spend cap is reached.
        """
        ...
