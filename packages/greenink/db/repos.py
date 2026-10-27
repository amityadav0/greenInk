"""Persistence for the pipeline and the API. Every function takes an `AsyncSession` and speaks
the contract models in `greenink.core`; rows never leave this module.

Writes are idempotent on the keys in SPEC "Data model", so a retried job is safe.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from greenink.core.enums import (
    AnalysisStatus,
    CompanyDocumentKind,
    CompanySource,
    Stage,
    StageState,
    Verdict,
    VerifiedLevel,
)
from greenink.core.ids import new_id
from greenink.core.models import (
    Analysis,
    Company,
    CompanyDocument,
    CompanyFact,
    CompanyProfile,
    Evidence,
    Finding,
    Fix,
    JobEvent,
    LLMCall,
    Page,
    PriceIntel,
    PriceSource,
    Requirement,
    Tender,
    TenderDocument,
    VerdictRule,
)
from greenink.db.models import (
    AnalysisRow,
    CompanyDocumentRow,
    CompanyRow,
    FindingRow,
    JobEventRow,
    LLMCallRow,
    PageRow,
    PriceIntelRow,
    RequirementRow,
    TenderDocumentRow,
    TenderRow,
)

# Tenders


def _tender(row: TenderRow) -> Tender:
    return Tender(
        id=row.id,
        source=row.source,
        source_ref=row.source_ref,
        title=row.title,
        buyer=row.buyer,
        value_inr=float(row.value_inr) if row.value_inr is not None else None,
        closes_at=row.closes_at,
        official_url=row.official_url,
        meta=row.meta or {},
    )


async def upsert_tenders(session: AsyncSession, tenders: list[Tender]) -> None:
    if not tenders:
        return
    rows = [
        {
            "id": t.id,
            "source": t.source,
            "source_ref": t.source_ref,
            "title": t.title,
            "buyer": t.buyer,
            "value_inr": Decimal(str(t.value_inr)) if t.value_inr is not None else None,
            "closes_at": t.closes_at,
            "official_url": str(t.official_url) if t.official_url else None,
            "meta": t.meta,
        }
        for t in tenders
    ]
    statement = insert(TenderRow).values(rows)
    await session.execute(
        statement.on_conflict_do_update(
            index_elements=["source", "source_ref"],
            set_={
                "title": statement.excluded.title,
                "buyer": statement.excluded.buyer,
                "value_inr": statement.excluded.value_inr,
                "closes_at": statement.excluded.closes_at,
                "official_url": statement.excluded.official_url,
                "meta": statement.excluded.meta,
                "updated_at": func.now(),
            },
        )
    )


async def get_tender(session: AsyncSession, tender_id: UUID) -> Tender | None:
    row = await session.get(TenderRow, tender_id)
    return _tender(row) if row else None


# Tender documents and pages


@dataclass(frozen=True)
class StoredDocument:
    document: TenderDocument
    blob_key: str
    source_url: str | None
    extracted_version: str | None


def _stored(row: TenderDocumentRow) -> StoredDocument:
    return StoredDocument(
        document=TenderDocument(
            id=row.id,
            tender_id=row.tender_id,
            sha256=row.sha256,
            filename=row.filename,
            page_count=row.page_count,
        ),
        blob_key=row.blob_key,
        source_url=row.source_url,
        extracted_version=row.extracted_version,
    )


async def add_document(
    session: AsyncSession,
    tender_id: UUID,
    sha256: str,
    filename: str,
    blob_key: str,
    source_url: str | None = None,
) -> StoredDocument | None:
    """Insert a document; None when the same bytes are already stored (sha256 is unique)."""
    statement = (
        insert(TenderDocumentRow)
        .values(
            id=new_id(),
            tender_id=tender_id,
            sha256=sha256,
            filename=filename,
            blob_key=blob_key,
            source_url=source_url,
        )
        .on_conflict_do_nothing(index_elements=["sha256"])
        .returning(TenderDocumentRow)
    )
    row = (await session.execute(statement)).scalar_one_or_none()
    return _stored(row) if row else None


async def tender_documents(session: AsyncSession, tender_id: UUID) -> list[StoredDocument]:
    rows = await session.scalars(
        select(TenderDocumentRow)
        .where(TenderDocumentRow.tender_id == tender_id)
        .order_by(TenderDocumentRow.created_at, TenderDocumentRow.filename)
    )
    return [_stored(row) for row in rows]


async def get_document(session: AsyncSession, document_id: UUID) -> StoredDocument | None:
    row = await session.get(TenderDocumentRow, document_id)
    return _stored(row) if row else None


async def save_pages(session: AsyncSession, document_id: UUID, pages: list[Page]) -> None:
    await session.execute(delete(PageRow).where(PageRow.document_id == document_id))
    if pages:
        await session.execute(
            insert(PageRow).values(
                [
                    {"document_id": document_id, "page_no": p.page_no, "text": p.text, "method": p.method}
                    for p in pages
                ]
            )
        )
    await session.execute(
        update(TenderDocumentRow).where(TenderDocumentRow.id == document_id).values(page_count=len(pages))
    )


async def get_pages(session: AsyncSession, document_id: UUID) -> list[Page]:
    rows = await session.scalars(
        select(PageRow).where(PageRow.document_id == document_id).order_by(PageRow.page_no)
    )
    return [Page(document_id=r.document_id, page_no=r.page_no, text=r.text, method=r.method) for r in rows]


async def get_page(session: AsyncSession, document_id: UUID, page_no: int) -> Page | None:
    row = await session.get(PageRow, (document_id, page_no))
    return (
        Page(document_id=row.document_id, page_no=row.page_no, text=row.text, method=row.method)
        if row
        else None
    )


# Requirements


def _requirement(row: RequirementRow) -> Requirement:
    return Requirement(
        id=row.id,
        document_id=row.document_id,
        extractor_version=row.extractor_version,
        category=row.category,
        text=row.text,
        page_no=row.page_no,
        quote=row.quote,
        verified=row.verified,
    )


async def save_requirements(
    session: AsyncSession, document_id: UUID, version: str, requirements: list[Requirement]
) -> None:
    """Replace this document's requirements for `version` and mark it extracted."""
    await session.execute(
        delete(RequirementRow).where(
            RequirementRow.document_id == document_id, RequirementRow.extractor_version == version
        )
    )
    if requirements:
        await session.execute(
            insert(RequirementRow)
            .values(
                [
                    {
                        "id": r.id,
                        "document_id": document_id,
                        "extractor_version": version,
                        "category": r.category,
                        "text": r.text,
                        "page_no": r.page_no,
                        "quote": r.quote,
                        "verified": r.verified,
                    }
                    for r in requirements
                ]
            )
            .on_conflict_do_nothing(index_elements=["id"])
        )
    await session.execute(
        update(TenderDocumentRow).where(TenderDocumentRow.id == document_id).values(extracted_version=version)
    )


async def tender_requirements(session: AsyncSession, tender_id: UUID, version: str) -> list[Requirement]:
    rows = await session.scalars(
        select(RequirementRow)
        .join(TenderDocumentRow, TenderDocumentRow.id == RequirementRow.document_id)
        .where(TenderDocumentRow.tender_id == tender_id, RequirementRow.extractor_version == version)
        .order_by(TenderDocumentRow.created_at, RequirementRow.page_no)
    )
    return [_requirement(row) for row in rows]


# Companies


def _company(row: CompanyRow) -> Company:
    return Company(
        id=row.id,
        name=row.name,
        profile=CompanyProfile.model_validate(row.profile),
        source=row.source,
        verified_level=row.verified_level,
        read_only=row.session_id is None,
    )


@dataclass(frozen=True)
class OwnedCompany:
    company: Company
    session_id: str | None

    def visible_to(self, session_id: str | None) -> bool:
        """Shared demo companies (no session) are visible to all; others only to their session."""
        return self.session_id is None or self.session_id == session_id


async def get_company(session: AsyncSession, company_id: UUID) -> OwnedCompany | None:
    row = await session.get(CompanyRow, company_id)
    return OwnedCompany(_company(row), row.session_id) if row else None


async def list_companies(session: AsyncSession, session_id: str | None) -> list[Company]:
    query = select(CompanyRow).where(
        (CompanyRow.session_id.is_(None)) | (CompanyRow.session_id == session_id)
    )
    rows = await session.scalars(query.order_by(CompanyRow.session_id.is_not(None), CompanyRow.created_at))
    return [_company(row) for row in rows]


async def save_company(
    session: AsyncSession,
    *,
    company_id: UUID,
    name: str,
    profile: CompanyProfile,
    source: CompanySource,
    verified_level: VerifiedLevel,
    session_id: str | None,
) -> Company:
    values = {
        "id": company_id,
        "name": name,
        "profile": profile.model_dump(mode="json"),
        "source": source,
        "verified_level": verified_level,
        "session_id": session_id,
    }
    statement = insert(CompanyRow).values(values)
    await session.execute(
        statement.on_conflict_do_update(
            index_elements=["id"],
            set_={k: statement.excluded[k] for k in ("name", "profile", "source", "verified_level")}
            | {"updated_at": func.now()},
        )
    )
    row = await session.get(CompanyRow, company_id, populate_existing=True)
    assert row is not None
    return _company(row)


async def add_company_document(
    session: AsyncSession, company_id: UUID, kind: CompanyDocumentKind, filename: str, blob_key: str
) -> CompanyDocument:
    row = CompanyDocumentRow(
        id=new_id(), company_id=company_id, kind=kind, filename=filename, blob_key=blob_key
    )
    session.add(row)
    await session.flush()
    return CompanyDocument(id=row.id, company_id=company_id, kind=kind, filename=filename, facts=[])


@dataclass(frozen=True)
class StoredCompanyDocument:
    document: CompanyDocument
    blob_key: str


async def company_documents(session: AsyncSession, company_id: UUID) -> list[StoredCompanyDocument]:
    rows = await session.scalars(
        select(CompanyDocumentRow)
        .where(CompanyDocumentRow.company_id == company_id)
        .order_by(CompanyDocumentRow.created_at)
    )
    return [
        StoredCompanyDocument(
            CompanyDocument(
                id=r.id,
                company_id=r.company_id,
                kind=r.kind,
                filename=r.filename,
                facts=[CompanyFact.model_validate(f) for f in r.facts or []],
            ),
            r.blob_key,
        )
        for r in rows
    ]


async def set_company_document_facts(
    session: AsyncSession, document_id: UUID, facts: list[CompanyFact]
) -> None:
    await session.execute(
        update(CompanyDocumentRow)
        .where(CompanyDocumentRow.id == document_id)
        .values(facts=[f.model_dump(mode="json") for f in facts])
    )


# Analyses


def _analysis(row: AnalysisRow) -> Analysis:
    return Analysis(
        id=row.id,
        tender_id=row.tender_id,
        company_id=row.company_id,
        status=row.status,
        verdict=row.verdict,
        verdict_reason=row.verdict_reason,
        verdict_rules=[VerdictRule.model_validate(r) for r in row.verdict_rules or []],
        profile_hash=row.profile_hash,
        requirements_version=row.requirements_version,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


async def find_or_create_analysis(
    session: AsyncSession, tender_id: UUID, company_id: UUID, profile_hash: str, requirements_version: str
) -> tuple[Analysis, bool]:
    """The analysis for this cache key, and whether it was just created."""
    statement = (
        insert(AnalysisRow)
        .values(
            id=new_id(),
            tender_id=tender_id,
            company_id=company_id,
            status=AnalysisStatus.QUEUED,
            profile_hash=profile_hash,
            requirements_version=requirements_version,
        )
        .on_conflict_do_nothing(
            index_elements=["tender_id", "company_id", "profile_hash", "requirements_version"]
        )
        .returning(AnalysisRow)
    )
    created = (await session.execute(statement)).scalar_one_or_none()
    if created is not None:
        return _analysis(created), True
    row = await session.scalar(
        select(AnalysisRow).where(
            AnalysisRow.tender_id == tender_id,
            AnalysisRow.company_id == company_id,
            AnalysisRow.profile_hash == profile_hash,
            AnalysisRow.requirements_version == requirements_version,
        )
    )
    assert row is not None
    return _analysis(row), False


async def find_analysis(
    session: AsyncSession, tender_id: UUID, company_id: UUID, profile_hash: str, requirements_version: str
) -> Analysis | None:
    """The analysis stored under this cache key, if any."""
    row = await session.scalar(
        select(AnalysisRow).where(
            AnalysisRow.tender_id == tender_id,
            AnalysisRow.company_id == company_id,
            AnalysisRow.profile_hash == profile_hash,
            AnalysisRow.requirements_version == requirements_version,
        )
    )
    return _analysis(row) if row else None


async def get_analysis(session: AsyncSession, analysis_id: UUID) -> Analysis | None:
    row = await session.get(AnalysisRow, analysis_id, populate_existing=True)
    return _analysis(row) if row else None


async def set_analysis_status(session: AsyncSession, analysis_id: UUID, status: AnalysisStatus) -> None:
    await session.execute(
        update(AnalysisRow).where(AnalysisRow.id == analysis_id).values(status=status, updated_at=func.now())
    )


async def set_verdict(
    session: AsyncSession,
    analysis_id: UUID,
    status: AnalysisStatus,
    verdict: Verdict | None,
    reason: str | None,
    rules: list[VerdictRule],
) -> None:
    await session.execute(
        update(AnalysisRow)
        .where(AnalysisRow.id == analysis_id)
        .values(
            status=status,
            verdict=verdict,
            verdict_reason=reason,
            verdict_rules=[r.model_dump(mode="json") for r in rules],
            updated_at=func.now(),
        )
    )


async def analyses_waiting_for(session: AsyncSession, tender_id: UUID) -> list[UUID]:
    rows = await session.scalars(
        select(AnalysisRow.id).where(
            AnalysisRow.tender_id == tender_id,
            AnalysisRow.status.in_([AnalysisStatus.QUEUED, AnalysisStatus.RUNNING]),
        )
    )
    return list(rows)


async def save_findings(session: AsyncSession, analysis_id: UUID, findings: list[Finding]) -> None:
    await session.execute(delete(FindingRow).where(FindingRow.analysis_id == analysis_id))
    if findings:
        await session.execute(
            insert(FindingRow).values(
                [
                    {
                        "id": f.id,
                        "analysis_id": analysis_id,
                        "requirement_id": f.requirement.id,
                        "status": f.status,
                        "severity": f.severity,
                        "reason": f.reason,
                        "evidence": f.evidence.model_dump(mode="json"),
                        "fixable_before_close": f.fixable_before_close,
                        "fix": f.fix.model_dump(mode="json") if f.fix else None,
                    }
                    for f in findings
                ]
            )
        )


async def findings(session: AsyncSession, analysis_id: UUID) -> list[Finding]:
    rows = (
        await session.execute(
            select(FindingRow, RequirementRow)
            .join(RequirementRow, RequirementRow.id == FindingRow.requirement_id)
            .where(FindingRow.analysis_id == analysis_id)
        )
    ).all()
    return [
        Finding(
            id=f.id,
            analysis_id=f.analysis_id,
            requirement=_requirement(r),
            status=f.status,
            severity=f.severity,
            reason=f.reason,
            evidence=Evidence.model_validate(f.evidence),
            fixable_before_close=f.fixable_before_close,
            fix=Fix.model_validate(f.fix) if f.fix else None,
        )
        for f, r in rows
    ]


async def set_fix(session: AsyncSession, finding_id: UUID, fix: Fix) -> None:
    await session.execute(
        update(FindingRow).where(FindingRow.id == finding_id).values(fix=fix.model_dump(mode="json"))
    )


async def save_price_intel(session: AsyncSession, intel: PriceIntel) -> None:
    values = {
        "id": new_id(),
        "analysis_id": intel.analysis_id,
        "item": intel.item,
        "band_low": Decimal(str(intel.band_low)) if intel.band_low is not None else None,
        "band_high": Decimal(str(intel.band_high)) if intel.band_high is not None else None,
        "sources": [s.model_dump(mode="json") for s in intel.sources],
    }
    statement = insert(PriceIntelRow).values(values)
    await session.execute(
        statement.on_conflict_do_update(
            index_elements=["analysis_id", "item"],
            set_={k: statement.excluded[k] for k in ("band_low", "band_high", "sources")},
        )
    )


async def price_intel(session: AsyncSession, analysis_id: UUID) -> list[PriceIntel]:
    rows = await session.scalars(select(PriceIntelRow).where(PriceIntelRow.analysis_id == analysis_id))
    return [
        PriceIntel(
            analysis_id=r.analysis_id,
            item=r.item,
            band_low=float(r.band_low) if r.band_low is not None else None,
            band_high=float(r.band_high) if r.band_high is not None else None,
            sources=[PriceSource.model_validate(s) for s in r.sources or []],
        )
        for r in rows
    ]


# Events and trace


async def add_event(
    session: AsyncSession, analysis_id: UUID, stage: Stage, state: StageState, message: str
) -> tuple[int, JobEvent]:
    row = JobEventRow(
        analysis_id=analysis_id, stage=stage, state=state, message=message, at=datetime.now(UTC)
    )
    session.add(row)
    await session.flush()
    return row.id, JobEvent(analysis_id=analysis_id, stage=stage, state=state, message=message, at=row.at)


async def events_after(
    session: AsyncSession, analysis_id: UUID, after_id: int = 0
) -> list[tuple[int, JobEvent]]:
    rows = await session.scalars(
        select(JobEventRow)
        .where(JobEventRow.analysis_id == analysis_id, JobEventRow.id > after_id)
        .order_by(JobEventRow.id)
    )
    return [
        (r.id, JobEvent(analysis_id=r.analysis_id, stage=r.stage, state=r.state, message=r.message, at=r.at))
        for r in rows
    ]


async def llm_calls(session: AsyncSession, analysis_id: UUID) -> list[LLMCall]:
    rows = await session.scalars(
        select(LLMCallRow).where(LLMCallRow.analysis_id == analysis_id).order_by(LLMCallRow.created_at)
    )
    return [
        LLMCall(
            id=r.id,
            analysis_id=r.analysis_id,
            task=r.task,
            model=r.model,
            tokens_in=r.tokens_in,
            tokens_out=r.tokens_out,
            cost_usd=float(r.cost_usd),
            latency_ms=r.latency_ms,
            status=r.status,
            prompt_hash=r.prompt_hash,
            created_at=r.created_at,
        )
        for r in rows
    ]
