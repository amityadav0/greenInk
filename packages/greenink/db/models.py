"""SQLAlchemy models for every table in SPEC "Data model".

Tender-side rows (tenders, documents, pages, requirements) are shared by every company.
Company-side rows (analyses and below) are per tender x company. PDFs live in blob storage.
Enums are stored as strings with a CHECK constraint, so adding a value is a plain migration.
"""

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any, ClassVar
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    MetaData,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from greenink.core.enums import (
    AnalysisStatus,
    CompanyDocumentKind,
    CompanySource,
    FindingStatus,
    LLMCallStatus,
    LLMTask,
    PageMethod,
    RequirementCategory,
    Severity,
    Stage,
    StageState,
    TenderSource,
    Verdict,
    VerifiedLevel,
)

NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


def _enum[E: StrEnum](enum: type[E], name: str) -> SAEnum:
    return SAEnum(
        enum,
        name=name,
        native_enum=False,
        create_constraint=True,
        length=32,
        values_callable=lambda members: [member.value for member in members],
        validate_strings=True,
    )


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)
    type_annotation_map: ClassVar[dict[Any, Any]] = {
        datetime: DateTime(timezone=True),
        dict[str, Any]: JSONB,
        list[Any]: JSONB,
    }


class _Timestamps:
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class _Updated(_Timestamps):
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())


# Tender side: computed once per document, shared by every company.


class TenderRow(_Updated, Base):
    __tablename__ = "tenders"
    __table_args__ = (UniqueConstraint("source", "source_ref"),)

    id: Mapped[UUID] = mapped_column(primary_key=True)
    source: Mapped[TenderSource] = mapped_column(_enum(TenderSource, "tender_source"))
    source_ref: Mapped[str] = mapped_column(String(200))
    title: Mapped[str] = mapped_column(Text)
    buyer: Mapped[str | None] = mapped_column(Text)
    value_inr: Mapped[Decimal | None] = mapped_column(Numeric(16, 2))
    closes_at: Mapped[datetime | None]
    official_url: Mapped[str | None] = mapped_column(Text)
    meta: Mapped[dict[str, Any]] = mapped_column(server_default="{}")


class TenderDocumentRow(_Timestamps, Base):
    __tablename__ = "tender_documents"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    tender_id: Mapped[UUID] = mapped_column(ForeignKey("tenders.id", ondelete="CASCADE"), index=True)
    sha256: Mapped[str] = mapped_column(String(64), unique=True)
    filename: Mapped[str] = mapped_column(Text)
    blob_key: Mapped[str] = mapped_column(Text)
    page_count: Mapped[int | None]


class PageRow(Base):
    __tablename__ = "pages"
    __table_args__ = (CheckConstraint("page_no >= 1", name="page_no_positive"),)

    document_id: Mapped[UUID] = mapped_column(
        ForeignKey("tender_documents.id", ondelete="CASCADE"), primary_key=True
    )
    page_no: Mapped[int] = mapped_column(primary_key=True)
    text: Mapped[str] = mapped_column(Text)
    method: Mapped[PageMethod] = mapped_column(_enum(PageMethod, "page_method"))


class RequirementRow(_Timestamps, Base):
    __tablename__ = "requirements"
    __table_args__ = (
        # Extraction cache key: (document.sha256, extractor_version); sha256 is per document.
        Index(None, "document_id", "extractor_version"),
        CheckConstraint("page_no >= 1", name="page_no_positive"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    document_id: Mapped[UUID] = mapped_column(ForeignKey("tender_documents.id", ondelete="CASCADE"))
    extractor_version: Mapped[str] = mapped_column(String(64))
    category: Mapped[RequirementCategory] = mapped_column(_enum(RequirementCategory, "requirement_category"))
    text: Mapped[str] = mapped_column(Text)
    page_no: Mapped[int]
    quote: Mapped[str] = mapped_column(Text)
    verified: Mapped[bool] = mapped_column(server_default="false")


# Company side.


class CompanyRow(_Updated, Base):
    __tablename__ = "companies"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    profile: Mapped[dict[str, Any]]
    source: Mapped[CompanySource] = mapped_column(_enum(CompanySource, "company_source"))
    verified_level: Mapped[VerifiedLevel] = mapped_column(_enum(VerifiedLevel, "verified_level"))
    session_id: Mapped[str | None] = mapped_column(
        String(64), index=True, comment="Owning anonymous session; NULL for the shared demo company."
    )


class CompanyDocumentRow(_Timestamps, Base):
    __tablename__ = "company_documents"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    company_id: Mapped[UUID] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    kind: Mapped[CompanyDocumentKind] = mapped_column(_enum(CompanyDocumentKind, "company_document_kind"))
    filename: Mapped[str] = mapped_column(Text)
    blob_key: Mapped[str] = mapped_column(Text)
    facts: Mapped[list[Any]] = mapped_column(server_default="[]")


# Per tender x company.


class AnalysisRow(_Updated, Base):
    __tablename__ = "analyses"
    __table_args__ = (
        # Analysis cache key: a second open of the same report is served from this row.
        UniqueConstraint("tender_id", "company_id", "profile_hash", "requirements_version"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    tender_id: Mapped[UUID] = mapped_column(ForeignKey("tenders.id", ondelete="CASCADE"))
    company_id: Mapped[UUID] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    status: Mapped[AnalysisStatus] = mapped_column(_enum(AnalysisStatus, "analysis_status"))
    verdict: Mapped[Verdict | None] = mapped_column(_enum(Verdict, "verdict"))
    verdict_reason: Mapped[str | None] = mapped_column(Text)
    verdict_rules: Mapped[list[Any]] = mapped_column(server_default="[]")
    profile_hash: Mapped[str] = mapped_column(String(64))
    requirements_version: Mapped[str] = mapped_column(String(128))


class FindingRow(_Timestamps, Base):
    __tablename__ = "findings"
    __table_args__ = (UniqueConstraint("analysis_id", "requirement_id"),)

    id: Mapped[UUID] = mapped_column(primary_key=True)
    analysis_id: Mapped[UUID] = mapped_column(ForeignKey("analyses.id", ondelete="CASCADE"))
    requirement_id: Mapped[UUID] = mapped_column(
        ForeignKey("requirements.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[FindingStatus] = mapped_column(_enum(FindingStatus, "finding_status"))
    severity: Mapped[Severity] = mapped_column(_enum(Severity, "severity"))
    reason: Mapped[str] = mapped_column(Text)
    evidence: Mapped[dict[str, Any]]
    fixable_before_close: Mapped[bool | None]
    fix: Mapped[dict[str, Any] | None]


class PriceIntelRow(_Timestamps, Base):
    __tablename__ = "price_intel"
    __table_args__ = (UniqueConstraint("analysis_id", "item"),)

    id: Mapped[UUID] = mapped_column(primary_key=True)
    analysis_id: Mapped[UUID] = mapped_column(ForeignKey("analyses.id", ondelete="CASCADE"))
    item: Mapped[str] = mapped_column(Text)
    band_low: Mapped[Decimal | None] = mapped_column(Numeric(16, 2))
    band_high: Mapped[Decimal | None] = mapped_column(Numeric(16, 2))
    sources: Mapped[list[Any]] = mapped_column(server_default="[]")


# Gateway and pipeline bookkeeping.


class LLMCallRow(_Timestamps, Base):
    __tablename__ = "llm_calls"
    __table_args__ = (Index(None, "created_at"),)  # daily spend cap

    id: Mapped[UUID] = mapped_column(primary_key=True)
    # SET NULL, not CASCADE: deleting an analysis keeps the spend history for budgets.
    analysis_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("analyses.id", ondelete="SET NULL"), index=True
    )
    task: Mapped[LLMTask] = mapped_column(_enum(LLMTask, "llm_task"))
    model: Mapped[str] = mapped_column(String(200))
    tokens_in: Mapped[int]
    tokens_out: Mapped[int]
    cost_usd: Mapped[Decimal] = mapped_column(Numeric(12, 6))
    latency_ms: Mapped[int]
    status: Mapped[LLMCallStatus] = mapped_column(_enum(LLMCallStatus, "llm_call_status"))
    # LLM cache key: exact repeats are served from `output`.
    prompt_hash: Mapped[str] = mapped_column(String(64), index=True)
    output: Mapped[dict[str, Any] | None]
    error: Mapped[str | None] = mapped_column(Text)


class JobEventRow(Base):
    __tablename__ = "job_events"
    __table_args__ = (Index(None, "analysis_id", "id"),)

    id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True, comment="Also the SSE event id."
    )
    analysis_id: Mapped[UUID] = mapped_column(ForeignKey("analyses.id", ondelete="CASCADE"))
    stage: Mapped[Stage] = mapped_column(_enum(Stage, "stage"))
    state: Mapped[StageState] = mapped_column(_enum(StageState, "stage_state"))
    message: Mapped[str] = mapped_column(Text)
    at: Mapped[datetime] = mapped_column(server_default=func.now())
