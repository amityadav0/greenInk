"""Profile building from uploaded company documents."""

from greenink.core.models import CompanyDocument, CompanyProfile
from greenink.llm.port import LLM


class DocumentProfileBuilder:
    def __init__(self, llm: LLM) -> None:
        self._llm = llm

    async def from_docs(self, documents: list[CompanyDocument]) -> CompanyProfile:
        raise NotImplementedError("TODO(lane-A): merge document facts into a CompanyProfile")

    async def from_url(self, url: str) -> CompanyProfile:
        raise NotImplementedError("TODO(lane-A): see companies.from_url")
