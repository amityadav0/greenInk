"""Request and response bodies for the `/v1` HTTP API (SPEC "API contract").

`contracts/openapi.yaml` is generated from the routes that use these models;
a test fails if the two drift apart.
"""

from typing import Literal
from uuid import UUID

from pydantic import Field, HttpUrl

from greenink.core.enums import AnalysisStatus, ErrorCode, PageMethod, Stage, StageState
from greenink.core.models import (
    Analysis,
    BidSummary,
    CompanyProfile,
    Contract,
    Finding,
    LLMCall,
    PageNo,
    PriceIntel,
    Sha256,
    Tender,
    TriageBadge,
)


class ErrorBody(Contract):
    """The one error shape. The web app shows `message` to users as written."""

    code: ErrorCode
    message: str
    retryable: bool


class Accepted(Contract):
    """Returned with `202` for long work. Progress is on `events_url` when present."""

    id: UUID
    status_url: str
    events_url: str | None = None
    cached: bool = Field(default=False, description="True when an existing result matched the cache key.")


class HealthStatus(Contract):
    status: Literal["ok"] = "ok"


class ReadyStatus(Contract):
    status: Literal["ok"] = "ok"
    checks: dict[str, bool] = Field(examples=[{"postgres": True, "redis": True}])


# Search


class SearchResponse(Contract):
    search_id: UUID
    query: str
    company_id: UUID | None = None
    cached: bool
    results: list[BidSummary]
    events_url: str = Field(description="SSE stream of triage badge updates for `results`.")


class SearchBadgeEvent(Contract):
    """SSE `data` for `event: badge`. The stream ends with `event: done`."""

    search_id: UUID
    source_ref: str
    badge: TriageBadge


# Tenders


class TenderDocumentOut(Contract):
    id: UUID
    sha256: Sha256
    filename: str
    page_count: int | None = Field(default=None, ge=0)
    download_url: str = Field(description="Short-lived signed URL to the PDF.")


class TenderDetail(Contract):
    tender: Tender
    documents: list[TenderDocumentOut]


class PageText(Contract):
    document_id: UUID
    page_no: PageNo
    text: str
    method: PageMethod


# Companies


class CompanyCreate(Contract):
    name: str = Field(min_length=1, max_length=200)
    profile: CompanyProfile


class CompanyFromUrl(Contract):
    url: HttpUrl


# Analyses


class AnalysisCreate(Contract):
    tender_id: UUID
    company_id: UUID


class StageStatus(Contract):
    stage: Stage
    state: StageState
    message: str | None = None


class AnalysisReport(Contract):
    """The full report: verdict, findings, price intel and stage states."""

    analysis: Analysis
    tender: Tender
    findings: list[Finding]
    price_intel: list[PriceIntel]
    stages: list[StageStatus]


class TraceTotals(Contract):
    tokens_in: int = Field(ge=0)
    tokens_out: int = Field(ge=0)
    cost_usd: float = Field(ge=0)
    latency_ms: int = Field(ge=0)


class AnalysisTrace(Contract):
    analysis_id: UUID
    status: AnalysisStatus
    calls: list[LLMCall]
    totals: TraceTotals
