"""Port of the `docs` module: PDF bytes to page-tagged text."""

from dataclasses import dataclass
from typing import Protocol

from greenink.core.enums import PageMethod

MIN_TEXT_CHARS = 50
"""Pages with less text than this go to vision OCR (SPEC "Pipeline and jobs")."""


@dataclass(frozen=True)
class ParsedPage:
    page_no: int
    text: str
    method: PageMethod


Pages = list[ParsedPage]


class Parser(Protocol):
    async def parse(self, data: bytes) -> Pages: ...
