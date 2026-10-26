"""Domain entities: the frozen contract shared by the API, the pipeline and the web client.

Every model here is exported as a JSON Schema to `contracts/schemas/` (`make openapi`).
Changing a field is a contract change: note it in the PR and regenerate the web client.
"""

from datetime import date
from typing import Annotated, Any
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, HttpUrl

from greenink.core.enums import (
    AnalysisStatus,
    BusinessNature,
    CertificationKind,
    CompanyDocumentKind,
    CompanySource,
    FindingStatus,
    FixKind,
    LLMCallStatus,
    LLMTask,
    MSECategory,
    PageMethod,
    RequirementCategory,
    Severity,
    Stage,
    StageState,
    TenderSource,
    TriageLevel,
    Verdict,
    VerifiedLevel,
)

PageNo = Annotated[int, Field(ge=1, description="1-based page number in the source PDF.")]
Sha256 = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
Inr = Annotated[float, Field(ge=0, description="Amount in Indian rupees.")]


class Contract(BaseModel):
    """Base for contract models: unknown fields are rejected, so drift fails loudly."""

    model_config = ConfigDict(extra="forbid")


# Tenders


class Tender(Contract):
    id: UUID
    source: TenderSource
    source_ref: str = Field(description="The source's own id, e.g. a GeM bid number.")
    title: str
    buyer: str | None = None
    value_inr: Inr | None = Field(default=None, description="Estimated bid value, when published.")
    closes_at: AwareDatetime | None = None
    official_url: HttpUrl | None = Field(
        default=None, description="Official page of the bid; every bid links back to its source."
    )
    meta: dict[str, Any] = Field(default_factory=dict, description="Source-specific fields.")


class TenderDocument(Contract):
    id: UUID
    tender_id: UUID
    sha256: Sha256
    filename: str
    page_count: int | None = Field(default=None, ge=0)


class Page(Contract):
    document_id: UUID
    page_no: PageNo
    text: str
    method: PageMethod


class Requirement(Contract):
    """A requirement extracted from a tender document. Shared by every company."""

    id: UUID
    document_id: UUID
    extractor_version: str
    category: RequirementCategory
    text: str = Field(description="The requirement, restated in one plain sentence.")
    page_no: PageNo
    quote: str = Field(description="Verbatim text from the cited page.")
    verified: bool = Field(description="True when the quote fuzzy-matches the cited page.")


# Companies


class MSEStatus(Contract):
    udyam_registered: bool
    category: MSECategory | None = None


class TurnoverYear(Contract):
    fiscal_year: str = Field(pattern=r"^\d{4}-\d{2}$", examples=["2024-25"])
    amount_inr: Inr


class PastSupply(Contract):
    buyer: str
    item: str
    quantity: int | None = Field(default=None, ge=0)
    value_inr: Inr | None = None
    year: int | None = Field(default=None, ge=1900, le=2100)


class Certification(Contract):
    kind: CertificationKind
    name: str = Field(description="As written on the certificate, e.g. 'IS 16227'.")
    scope: str | None = None
    valid_until: date | None = None


class CompanyProfile(Contract):
    """What judging compares each requirement against."""

    legal_name: str
    business_nature: BusinessNature = BusinessNature.UNKNOWN
    business_nature_wording: str | None = Field(
        default=None,
        description="Exact wording on the company's papers, e.g. 'Trading Business'.",
    )
    constitution: str | None = Field(default=None, examples=["proprietorship", "private_limited"])
    state: str | None = None
    msme: MSEStatus | None = None
    startup_recognised: bool = False
    products: list[str] = Field(default_factory=list)
    annual_turnover: list[TurnoverYear] = Field(default_factory=list)
    years_in_operation: int | None = Field(default=None, ge=0)
    past_supplies: list[PastSupply] = Field(default_factory=list)
    certifications: list[Certification] = Field(default_factory=list)
    oem_authorisations: list[str] = Field(default_factory=list)
    website: HttpUrl | None = None


class Company(Contract):
    id: UUID
    name: str
    profile: CompanyProfile
    source: CompanySource
    verified_level: VerifiedLevel
    read_only: bool = Field(description="True for the shared demo company.")


class CompanyFact(Contract):
    """A fact read from a company document, with where it was found."""

    key: str = Field(examples=["business_nature_wording", "annual_turnover.2024-25"])
    value: str
    page_no: PageNo | None = None
    quote: str | None = None


class CompanyDocument(Contract):
    id: UUID
    company_id: UUID
    kind: CompanyDocumentKind
    filename: str
    facts: list[CompanyFact] = Field(default_factory=list)


# Analyses


class EvidenceQuote(Contract):
    company_document_id: UUID
    page_no: PageNo | None = None
    quote: str


class Evidence(Contract):
    company_has: str = Field(description="What the company has against this requirement, in one line.")
    quotes: list[EvidenceQuote] = Field(default_factory=list)


class Fix(Contract):
    kind: FixKind
    title: str
    body: str = Field(description="Markdown: the letter, checklist or document request.")
    steps: list[str] = Field(default_factory=list)


class Finding(Contract):
    id: UUID
    analysis_id: UUID
    requirement: Requirement
    status: FindingStatus
    severity: Severity
    reason: str = Field(description="Why this status, in one or two sentences.")
    evidence: Evidence
    fixable_before_close: bool | None = Field(
        default=None, description="Whether the gap can be closed before the bid closes; feeds the verdict."
    )
    fix: Fix | None = None


class VerdictRule(Contract):
    """One verdict rule that fired, with the findings that triggered it."""

    rule: str = Field(examples=["critical_unfixable", "fixable_gap", "no_blocking_gap"])
    verdict: Verdict
    finding_ids: list[UUID] = Field(default_factory=list)


class Analysis(Contract):
    """One tender judged for one company. Cached by
    `(tender_id, company_id, profile_hash, requirements_version)`."""

    id: UUID
    tender_id: UUID
    company_id: UUID
    status: AnalysisStatus
    verdict: Verdict | None = None
    verdict_reason: str | None = None
    verdict_rules: list[VerdictRule] = Field(default_factory=list)
    profile_hash: str
    requirements_version: str
    created_at: AwareDatetime
    updated_at: AwareDatetime


class PriceSource(Contract):
    title: str
    url: HttpUrl
    snippet: str | None = None
    price_inr: Inr | None = None
    observed_on: date | None = None
    provider: str = Field(examples=["tavily", "gem_results"])


class PriceIntel(Contract):
    analysis_id: UUID
    item: str
    band_low: Inr | None = None
    band_high: Inr | None = None
    sources: list[PriceSource] = Field(default_factory=list)


class LLMCall(Contract):
    """One row of the Model Trace."""

    id: UUID
    analysis_id: UUID | None = None
    task: LLMTask
    model: str = Field(description="The model that actually answered (after any fallback).")
    tokens_in: int = Field(ge=0)
    tokens_out: int = Field(ge=0)
    cost_usd: float = Field(ge=0)
    latency_ms: int = Field(ge=0)
    status: LLMCallStatus
    prompt_hash: str
    created_at: AwareDatetime


class JobEvent(Contract):
    """Stage progress; stored in `job_events` and streamed over SSE."""

    analysis_id: UUID
    stage: Stage
    state: StageState
    message: str = Field(examples=["Reading 64 pages…", "41 requirements found"])
    at: AwareDatetime


# Search


class TriageBadge(Contract):
    level: TriageLevel
    reason: str


class BidSummary(Contract):
    """A search result. Search stores tender metadata, so every result has a `tender_id`."""

    tender_id: UUID
    source: TenderSource
    source_ref: str
    title: str
    buyer: str | None = None
    quantity: int | None = Field(default=None, ge=0)
    closes_at: AwareDatetime | None = None
    value_inr: Inr | None = None
    official_url: HttpUrl | None = None
    badge: TriageBadge | None = Field(default=None, description="Null until triage scores it.")


# Model outputs: the schemas the LLM gateway validates against.


class ExtractedRequirement(Contract):
    category: RequirementCategory
    text: str
    page_no: PageNo
    quote: str


class ExtractionResult(Contract):
    """Output of the `extract` task for one document."""

    requirements: list[ExtractedRequirement]


class JudgedRequirement(Contract):
    """Output of the `judge` task for one requirement."""

    requirement_id: UUID
    status: FindingStatus
    severity: Severity
    reason: str
    evidence: Evidence
    fixable_before_close: bool | None = None


class JudgeResult(Contract):
    findings: list[JudgedRequirement]


class TriageScore(Contract):
    source_ref: str
    badge: TriageBadge


class TriageResult(Contract):
    """Output of the `triage` task for one batch of bids."""

    scores: list[TriageScore]
