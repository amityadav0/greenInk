"""Port of the `companies` module: company profiles from a website or from documents."""

from typing import Protocol

from pydantic import BaseModel, Field

from greenink.core.enums import CompanyDocumentKind
from greenink.core.models import CompanyFact, CompanyProfile
from greenink.docs.port import Pages


class DocumentReading(BaseModel):
    """What one company document adds: facts with their page, and the updated profile."""

    facts: list[CompanyFact] = Field(default_factory=list)
    profile: CompanyProfile


class WebsiteProfiler(Protocol):
    async def from_url(self, url: str) -> CompanyProfile:
        """Draft profile from a website; the company is stored as `unverified`."""
        ...


class DocumentReader(Protocol):
    async def from_document(
        self, profile: CompanyProfile, kind: CompanyDocumentKind, pages: Pages
    ) -> DocumentReading:
        """Read one uploaded document into facts, and merge them into `profile`."""
        ...
