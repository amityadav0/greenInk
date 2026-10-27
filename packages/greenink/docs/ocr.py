"""Vision transcription for scanned pages and BoQ tables, through the `page_vision` LLM task."""

from uuid import UUID

from pydantic import BaseModel, Field

from greenink.core.enums import LLMTask, PageMethod
from greenink.docs.port import ParsedPage
from greenink.llm.port import LLM, LLMInput

PROMPT_VERSION = "page_vision.v1"
INSTRUCTIONS = """\
You transcribe one page of a government tender document from an image.

Write out all the text on the page, in reading order, exactly as printed. Keep numbers, units,
clause numbers and punctuation as they are. Render tables row by row, with cells separated by
" | ". Transcribe English text; for text in other scripts, write [non-English text].
Do not summarise, translate, correct or add anything.

Return JSON with one field, "text"."""


class PageTranscript(BaseModel):
    text: str = Field(description="Everything printed on the page, in reading order.")


async def read_page(llm: LLM, page_no: int, image_png: bytes, analysis_id: UUID | None = None) -> ParsedPage:
    result = await llm.run(
        LLMTask.PAGE_VISION,
        LLMInput(instructions=INSTRUCTIONS, images=[image_png]),
        PageTranscript,
        analysis_id=analysis_id,
    )
    return ParsedPage(page_no=page_no, text=result.output.text, method=PageMethod.VISION)
