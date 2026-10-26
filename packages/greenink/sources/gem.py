"""GeM bidplus adapter (bidplus.gem.gov.in). See `scripts/gem_spike.py` for the request flow."""

from greenink.core.enums import TenderSource
from greenink.sources.base import SourceBid, TenderDoc


class GemBidplusAdapter:
    source = TenderSource.GEM

    async def search(self, query: str) -> list[SourceBid]:
        # TODO(lane-C): port the spike's search flow; 1 req/s; project user agent; Redis cache.
        raise NotImplementedError("TODO(lane-C): GemBidplusAdapter.search")

    async def fetch(self, ref: str) -> TenderDoc:
        raise NotImplementedError("TODO(lane-C): GemBidplusAdapter.fetch")
