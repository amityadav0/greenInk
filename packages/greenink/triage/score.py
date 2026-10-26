"""Win-ability badges with the `triage` task, in batches of `BATCH_SIZE`."""

from greenink.core.models import BidSummary, CompanyProfile, TriageBadge
from greenink.llm.port import LLM


class LLMTriage:
    def __init__(self, llm: LLM) -> None:
        self._llm = llm

    async def score(self, bids: list[BidSummary], profile: CompanyProfile) -> dict[str, TriageBadge]:
        raise NotImplementedError("TODO(lane-A): Lightning scores bids in batches")
