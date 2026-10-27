"""Enumerations shared by the API contract, the database and the pipeline.

Values are part of the frozen contract (SPEC "Data model"): renaming or removing
one is a breaking change that needs a PR note and a regenerated web client.
"""

from enum import StrEnum


class TenderSource(StrEnum):
    """Where a tender came from. One value per `sources` adapter."""

    GEM = "gem"
    UPLOAD = "upload"


class PageMethod(StrEnum):
    """How a page's text was obtained."""

    TEXT = "text"
    VISION = "vision"


class RequirementCategory(StrEnum):
    TURNOVER = "turnover"
    EXPERIENCE = "experience"
    MSE_EXEMPTION = "mse_exemption"
    STARTUP_EXEMPTION = "startup_exemption"
    OEM_AUTHORISATION = "oem_authorisation"
    BIS_CERTIFICATION = "bis_certification"
    TYPE_TEST = "type_test"
    EMD = "emd"
    EPBG = "epbg"
    DOCUMENT = "document"
    DELIVERY = "delivery"
    ATC = "atc"
    BOQ_FORMAT = "boq_format"
    OTHER = "other"


class FindingStatus(StrEnum):
    PASS = "pass"  # noqa: S105  (a finding status, not a password)
    FAIL = "fail"
    MISSING_PROOF = "missing_proof"
    UNCLEAR = "unclear"


class Severity(StrEnum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class Verdict(StrEnum):
    BID = "bid"
    FIX_THEN_BID = "fix_then_bid"
    SKIP = "skip"


class AnalysisStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    PARTIAL = "partial"
    FAILED = "failed"


class CompanySource(StrEnum):
    """How a company profile was built."""

    DEMO = "demo"
    DOCS = "docs"
    URL = "url"


class VerifiedLevel(StrEnum):
    """How far a company profile is backed by documents.

    `unverified`: built from a website or typed in, no documents behind it.
    `partial`: some profile facts are backed by uploaded documents.
    `documented`: every profile fact used in judging is backed by a document.
    """

    UNVERIFIED = "unverified"
    PARTIAL = "partial"
    DOCUMENTED = "documented"


class CompanyDocumentKind(StrEnum):
    UDYAM_CERTIFICATE = "udyam_certificate"
    GST_CERTIFICATE = "gst_certificate"
    TURNOVER_CERTIFICATE = "turnover_certificate"
    BALANCE_SHEET = "balance_sheet"
    BIS_LICENCE = "bis_licence"
    ISO_CERTIFICATE = "iso_certificate"
    TYPE_TEST_REPORT = "type_test_report"
    OEM_AUTHORISATION = "oem_authorisation"
    EXPERIENCE_CERTIFICATE = "experience_certificate"
    STARTUP_RECOGNITION = "startup_recognition"
    OTHER = "other"


class BusinessNature(StrEnum):
    """What the company's papers say it does; tenders often require `manufacturer`."""

    MANUFACTURER = "manufacturer"
    TRADER = "trader"
    SERVICE_PROVIDER = "service_provider"
    UNKNOWN = "unknown"


class MSECategory(StrEnum):
    MICRO = "micro"
    SMALL = "small"
    MEDIUM = "medium"


class CertificationKind(StrEnum):
    BIS = "bis"
    ISO = "iso"
    TYPE_TEST = "type_test"
    NSIC = "nsic"
    OTHER = "other"


class FixKind(StrEnum):
    LETTER = "letter"
    CHECKLIST = "checklist"
    DOCUMENT_REQUEST = "document_request"


class TriageLevel(StrEnum):
    """Win-ability badge on a search result."""

    GREEN = "green"
    AMBER = "amber"
    RED = "red"


class Stage(StrEnum):
    """Pipeline stages (SPEC "Pipeline and jobs")."""

    INGEST = "ingest"
    PARSE = "parse"
    EXTRACT = "extract"
    VERIFY = "verify"
    JUDGE = "judge"
    VERDICT = "verdict"
    INTEL = "intel"
    TRIAGE = "triage"


class StageState(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    RETRYING = "retrying"
    DONE = "done"
    SKIPPED = "skipped"
    """Output was already stored under the stage's idempotency key."""
    FAILED = "failed"


class LLMTask(StrEnum):
    """Gateway tasks; each maps to a model in `config/models.yaml`."""

    TRIAGE = "triage"
    PROFILE_URL = "profile_url"
    EXTRACT = "extract"
    PAGE_VISION = "page_vision"
    JUDGE = "judge"
    FIX = "fix"
    PRICE_INTEL = "price_intel"


class LLMCallStatus(StrEnum):
    OK = "ok"
    CACHED = "cached"
    """Served from the `prompt_hash` cache; no tokens billed."""
    INVALID_OUTPUT = "invalid_output"
    """The model answered but the output failed schema validation after repair."""
    TIMEOUT = "timeout"
    ERROR = "error"
    BUDGET_EXCEEDED = "budget_exceeded"


class ErrorCode(StrEnum):
    """`code` values in the `{code, message, retryable}` error shape."""

    BAD_REQUEST = "bad_request"
    VALIDATION_ERROR = "validation_error"
    NOT_FOUND = "not_found"
    CONFLICT = "conflict"
    PAYLOAD_TOO_LARGE = "payload_too_large"
    UNSUPPORTED_MEDIA_TYPE = "unsupported_media_type"
    RATE_LIMITED = "rate_limited"
    BUDGET_EXCEEDED = "budget_exceeded"
    NOT_IMPLEMENTED = "not_implemented"
    UPSTREAM_UNAVAILABLE = "upstream_unavailable"
    NOT_READY = "not_ready"
    INTERNAL = "internal"
