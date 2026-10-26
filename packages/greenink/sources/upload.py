"""Manual upload adapter: any tender PDF, for portals we do not search (CPPP, state NIC)."""

from greenink.core.enums import TenderSource
from greenink.sources.base import SourceBid, TenderDoc


class UploadAdapter:
    source = TenderSource.UPLOAD

    async def search(self, query: str) -> list[SourceBid]:
        # Uploaded tenders are opened by id, never searched.
        return []

    async def fetch(self, ref: str) -> TenderDoc:
        # TODO(lane-C): read the uploaded blob; type checked from bytes; 25 MB cap.
        raise NotImplementedError("TODO(lane-C): UploadAdapter.fetch")
