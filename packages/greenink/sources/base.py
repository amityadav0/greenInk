"""Port of the `sources` module: finding tenders and fetching their documents."""

from dataclasses import dataclass
from typing import Protocol

from greenink.core.enums import TenderSource
from greenink.core.models import Tender


@dataclass(frozen=True)
class SourceBid:
    """A search hit as the source reports it, before it is stored as a `Tender`."""

    source: TenderSource
    source_ref: str
    title: str
    buyer: str | None
    quantity: int | None
    closes_at_iso: str | None
    value_inr: float | None
    official_url: str | None
    document_url: str | None


@dataclass(frozen=True)
class SourceFile:
    filename: str
    content: bytes


@dataclass(frozen=True)
class TenderDoc:
    """A tender with its documents' bytes, ready to hash and store."""

    tender: Tender
    files: list[SourceFile]


class SourceAdapter(Protocol):
    source: TenderSource

    async def search(self, query: str) -> list[SourceBid]:
        """Live search. Callers cache results by `(adapter, normalised query)`."""
        ...

    async def fetch(self, ref: str) -> TenderDoc:
        """Download a tender's documents by its `source_ref`."""
        ...
