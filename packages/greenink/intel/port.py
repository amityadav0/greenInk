"""Port of the `intel` module: price bands and buyer history."""

from typing import Protocol
from uuid import UUID

from greenink.core.models import PriceIntel


class IntelProvider(Protocol):
    async def prices(self, analysis_id: UUID, item: str, buyer: str | None) -> PriceIntel:
        """Price band for `item` with cited sources; buyer history when `buyer` is known."""
        ...
