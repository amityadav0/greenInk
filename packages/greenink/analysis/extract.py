"""Requirement extraction with the `extract` task (prompt: prompts/extract.vN.md)."""

from uuid import UUID

from greenink.core.models import Requirement
from greenink.docs.port import Pages
from greenink.llm.port import LLM


class LLMExtractor:
    version = "extract.v1"

    def __init__(self, llm: LLM) -> None:
        self._llm = llm

    async def extract(self, document_id: UUID, pages: Pages) -> list[Requirement]:
        raise NotImplementedError("TODO(lane-A): extract requirements with page + quote")
