"""Port of the `triage` module: fast win-ability scoring of search results."""

from typing import Protocol

from greenink.core.models import BidSummary, CompanyProfile, TriageBadge

BATCH_SIZE = 20


class Triage(Protocol):
    async def score(self, bids: list[BidSummary], profile: CompanyProfile) -> dict[str, TriageBadge]:
        """Badges keyed by `source_ref`."""
        ...
