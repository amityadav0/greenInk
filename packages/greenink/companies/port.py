"""Port of the `companies` module: company profiles from documents or a website."""

from typing import Protocol

from greenink.core.models import CompanyDocument, CompanyProfile


class ProfileBuilder(Protocol):
    async def from_docs(self, documents: list[CompanyDocument]) -> CompanyProfile: ...

    async def from_url(self, url: str) -> CompanyProfile:
        """Draft profile from a website; the company is stored as `unverified`."""
        ...
