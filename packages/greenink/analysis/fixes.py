"""Drafted fixes for failing findings, with the `fix` task."""

from greenink.core.models import CompanyProfile, Finding, Fix
from greenink.llm.port import LLM


class LLMFixer:
    def __init__(self, llm: LLM) -> None:
        self._llm = llm

    async def draft(self, finding: Finding, profile: CompanyProfile) -> Fix:
        raise NotImplementedError("TODO(lane-A): draft a letter, checklist or document request")
