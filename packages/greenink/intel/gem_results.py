"""Past award prices from GeM bid results (bidplus `/bidresultlists`)."""

from uuid import UUID

from greenink.core.models import PriceIntel


class GemResultsIntelProvider:
    async def prices(self, analysis_id: UUID, item: str, buyer: str | None) -> PriceIntel:
        raise NotImplementedError("TODO(lane-A): GeM bid results -> award prices")
