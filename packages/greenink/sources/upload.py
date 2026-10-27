"""Manual upload adapter: any tender PDF, for portals we do not search (CPPP, state NIC).

The API stores the uploaded file when it arrives, so there is nothing to fetch later.
"""

from greenink.core.enums import ErrorCode, TenderSource
from greenink.core.errors import GreenInkError
from greenink.core.models import Tender
from greenink.sources.base import TenderDoc

PDF_MAGIC = b"%PDF"


def check_upload(data: bytes, max_bytes: int) -> None:
    """Size and type from the bytes, never the file name."""
    if len(data) > max_bytes:
        raise GreenInkError(ErrorCode.PAYLOAD_TOO_LARGE, f"The file is over {max_bytes // (1024 * 1024)} MB.")
    if not data.startswith(PDF_MAGIC):
        raise GreenInkError(ErrorCode.UNSUPPORTED_MEDIA_TYPE, "Only PDF tenders can be uploaded.")


class UploadAdapter:
    source = TenderSource.UPLOAD

    async def search(self, query: str) -> list[Tender]:
        return []  # uploaded tenders are opened by id, never searched

    async def fetch(self, tender: Tender) -> TenderDoc:
        raise GreenInkError(ErrorCode.NOT_FOUND, "Uploaded tenders are stored when uploaded.")
