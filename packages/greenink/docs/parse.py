"""PyMuPDF text extraction, with vision OCR for pages that have no text layer."""

from greenink.docs.port import Pages
from greenink.llm.port import LLM


class PyMuPDFParser:
    def __init__(self, llm: LLM) -> None:
        self._llm = llm

    async def parse(self, data: bytes) -> Pages:
        # TODO(lane-A): PyMuPDF text per page; pages under MIN_TEXT_CHARS go to ocr.read_page.
        raise NotImplementedError("TODO(lane-A): PyMuPDFParser.parse")
