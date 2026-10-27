"""Port of the `sources` module: finding tenders and fetching their documents."""

from dataclasses import dataclass
from typing import Protocol

from greenink.core.enums import TenderSource
from greenink.core.models import Tender


@dataclass(frozen=True)
class SourceFile:
    filename: str
    content: bytes
    content_type: str
    source_url: str | None = None


@dataclass(frozen=True)
class TenderDoc:
    """A tender's documents: the main bid document first, then linked attachments."""

    tender: Tender
    files: list[SourceFile]


class SourceAdapter(Protocol):
    source: TenderSource

    async def search(self, query: str) -> list[Tender]:
        """Live search, most relevant first. Ids are deterministic per (source, source_ref);
        `meta` carries what `fetch` needs. Callers cache by `(adapter, normalised query)`."""
        ...

    async def fetch(self, tender: Tender) -> TenderDoc:
        """Download a tender's documents."""
        ...
