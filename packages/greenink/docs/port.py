"""Port of the `docs` module: PDF bytes to page-tagged text."""

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from greenink.core.enums import PageMethod

MIN_TEXT_CHARS = 50
"""Pages with less text than this go to vision OCR (SPEC "Pipeline and jobs")."""


@dataclass(frozen=True)
class ParsedPage:
    page_no: int
    text: str
    method: PageMethod


Pages = list[ParsedPage]


def render_pages(pages: Pages) -> str:
    """Pages as model input: each starts with a `=== PAGE n ===` line that citations refer to."""
    return "\n".join(f"=== PAGE {page.page_no} ===\n{page.text.strip()}" for page in pages)


class Parser(Protocol):
    async def parse(self, data: bytes, *, analysis_id: UUID | None = None) -> Pages:
        """`analysis_id` attributes any vision calls to that report's Model Trace."""
        ...
