"""Token Factory adapter for the `LLM` port."""

from uuid import UUID

from pydantic import BaseModel, SecretStr

from greenink.core.enums import LLMTask
from greenink.llm.port import LLMInput, LLMResult
from greenink.llm.router import ModelsConfig


class TokenFactoryGateway:
    """Calls Nebius Token Factory through the OpenAI-compatible API."""

    def __init__(self, config: ModelsConfig, api_key: SecretStr) -> None:
        self._config = config
        self._api_key = api_key

    async def run[T: BaseModel](
        self,
        task: LLMTask,
        input: LLMInput,
        schema: type[T],
        *,
        analysis_id: UUID | None = None,
    ) -> LLMResult[T]:
        # TODO(lane-A): routing with fallback, JSON output + one repair call, per-model
        # semaphores, budget check, delimited data blocks, `llm_calls` trace and prompt_hash cache.
        raise NotImplementedError("TODO(lane-A): TokenFactoryGateway.run")
