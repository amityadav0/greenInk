"""Vision OCR for scanned pages and BoQ tables, through the `page_vision` LLM task."""

from greenink.docs.port import ParsedPage
from greenink.llm.port import LLM


async def read_page(llm: LLM, page_no: int, image_png: bytes) -> ParsedPage:
    raise NotImplementedError("TODO(lane-A): page_vision call via llm.run")
