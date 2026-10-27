"""Ports of the `analysis` module: extract, verify, judge, fix."""

from datetime import datetime
from typing import Protocol
from uuid import UUID

from greenink.core.models import CompanyProfile, Finding, Fix, Requirement
from greenink.docs.port import Pages


class Extractor(Protocol):
    version: str
    """Part of the extraction cache key `(document.sha256, extractor_version)`."""

    async def extract(
        self, document_id: UUID, pages: Pages, *, analysis_id: UUID | None = None
    ) -> list[Requirement]: ...


class Verifier(Protocol):
    def verify(self, requirements: list[Requirement], pages: Pages) -> list[Requirement]:
        """Mark each requirement `verified` when its quote matches its cited page."""
        ...


class Judge(Protocol):
    async def judge(
        self,
        analysis_id: UUID,
        requirements: list[Requirement],
        profile: CompanyProfile,
        closes_at: datetime | None,
    ) -> list[Finding]:
        """Judge verified requirements only; never decides the verdict."""
        ...


class Fixer(Protocol):
    async def draft(
        self, finding: Finding, profile: CompanyProfile, *, analysis_id: UUID | None = None
    ) -> Fix: ...
