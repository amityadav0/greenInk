"""Per-requirement judging with the `judge` task."""

from datetime import datetime
from uuid import UUID

from greenink.core.models import CompanyProfile, Finding, Requirement
from greenink.llm.port import LLM


class LLMJudge:
    def __init__(self, llm: LLM) -> None:
        self._llm = llm

    async def judge(
        self,
        analysis_id: UUID,
        requirements: list[Requirement],
        profile: CompanyProfile,
        closes_at: datetime | None,
    ) -> list[Finding]:
        raise NotImplementedError("TODO(lane-A): judge verified requirements against the profile")
