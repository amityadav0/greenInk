"""Requirement extraction with the `extract` task (prompt: prompts/extract.v1.md)."""

import asyncio
from pathlib import Path
from uuid import UUID, uuid5

from greenink.analysis.verify import normalise
from greenink.core.enums import LLMTask
from greenink.core.models import ExtractionResult, Requirement
from greenink.docs.port import Pages, render_pages
from greenink.llm.port import LLM, LLMInput

PROMPTS = Path(__file__).parent / "prompts"
CHUNK_CHARS = 60_000
"""About 15k tokens of tender text per call; long documents are split on page boundaries."""


def load_prompt(version: str) -> str:
    return (PROMPTS / f"{version}.md").read_text(encoding="utf-8")


def chunk_pages(pages: Pages, limit: int = CHUNK_CHARS) -> list[Pages]:
    chunks: list[Pages] = []
    current: Pages = []
    size = 0
    for page in pages:
        if current and size + len(page.text) > limit:
            chunks.append(current)
            current, size = [], 0
        current.append(page)
        size += len(page.text)
    if current:
        chunks.append(current)
    return chunks


class LLMExtractor:
    version = "extract.v1"

    def __init__(self, llm: LLM) -> None:
        self._llm = llm
        self._instructions = load_prompt(self.version)

    async def extract(
        self, document_id: UUID, pages: Pages, *, analysis_id: UUID | None = None
    ) -> list[Requirement]:
        readable = [page for page in pages if page.text.strip()]
        if not readable:
            return []
        results = await asyncio.gather(
            *(
                self._llm.run(
                    LLMTask.EXTRACT,
                    LLMInput(instructions=self._instructions, data={"tender": render_pages(chunk)}),
                    ExtractionResult,
                    analysis_id=analysis_id,
                )
                for chunk in chunk_pages(readable)
            )
        )
        seen: set[tuple[str, int, str]] = set()
        requirements: list[Requirement] = []
        for result in results:
            for item in result.output.requirements:
                key = (item.category.value, item.page_no, normalise(item.quote))
                if key in seen:
                    continue
                seen.add(key)
                requirements.append(
                    Requirement(
                        # Deterministic: re-extracting a document yields the same ids, so judging
                        # inputs (and their prompt-cache keys) stay stable.
                        id=uuid5(document_id, f"{self.version}|{key[0]}|{key[1]}|{key[2]}"),
                        document_id=document_id,
                        extractor_version=self.version,
                        category=item.category,
                        text=item.text,
                        page_no=item.page_no,
                        quote=item.quote,
                        verified=False,
                    )
                )
        return requirements
