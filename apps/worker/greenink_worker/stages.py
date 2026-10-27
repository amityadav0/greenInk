"""Job handlers. Each is idempotent on its key (SPEC "Pipeline and jobs"): a stage that finds its
output already stored skips to the next stage, so retries and reruns are safe and free.

    ingest(source:ref) -> parse(sha256) per document -> extract(sha256:version) per document
      -> judge(analysis_id) once every document is extracted -> verdict (inline)
    intel(analysis_id) runs in parallel.
"""

import functools
import json
from collections.abc import Awaitable, Callable, Coroutine
from typing import Any
from uuid import UUID

import structlog
from arq import Retry

from greenink.analysis.verdict import decide
from greenink.core.enums import (
    AnalysisStatus,
    CompanySource,
    ErrorCode,
    FindingStatus,
    PageMethod,
    Stage,
    StageState,
    TenderSource,
    VerifiedLevel,
)
from greenink.core.errors import GreenInkError
from greenink.core.ids import sha256_hex
from greenink.core.models import BidSummary, Page
from greenink.db import repos
from greenink.docs.port import ParsedPage
from greenink.jobs.queue import JOB_QUEUE, MAX_TRIES, JobName, QueueName
from greenink_worker.wiring import Services

log = structlog.get_logger()

Handler = Callable[[dict[str, Any], str, dict[str, Any]], Coroutine[Any, Any, None]]
TRIAGE_TTL_S = 1800
EXTENSIONS = {"application/pdf": ".pdf", "image/png": ".png", "image/jpeg": ".jpg"}


def _services(ctx: dict[str, Any]) -> Services:
    services: Services = ctx["services"]
    return services


def _analysis_id(payload: dict[str, Any]) -> UUID | None:
    value = payload.get("analysis_id")
    return UUID(value) if value else None


def stage(
    name: Stage, *, report: bool = True
) -> Callable[[Callable[[Services, str, dict[str, Any]], Awaitable[None]]], Handler]:
    """Retries with backoff on retryable failures; after the last try (or on a permanent error)
    marks the stage failed with a human message, so the report shows what did finish.
    `report=False` is for on-demand work (fixes): it retries and logs but never touches the
    analysis's state or events."""

    def wrap(fn: Callable[[Services, str, dict[str, Any]], Awaitable[None]]) -> Handler:
        @functools.wraps(fn)
        async def handler(ctx: dict[str, Any], key: str, payload: dict[str, Any]) -> None:
            services = _services(ctx)
            attempt = int(ctx.get("job_try", 1))
            try:
                await fn(services, key, payload)
            except Exception as exc:
                retryable = exc.retryable if isinstance(exc, GreenInkError) else True
                message = (
                    exc.message if isinstance(exc, GreenInkError) else "An internal error stopped this step."
                )
                log.exception("stage_failed", stage=name, key=key, attempt=attempt, retryable=retryable)
                analysis_id = _analysis_id(payload) if report else None
                if retryable and attempt < MAX_TRIES:
                    if analysis_id:
                        await services.events.publish(
                            analysis_id,
                            name,
                            StageState.RETRYING,
                            f"Retrying after a hiccup ({attempt}/{MAX_TRIES - 1})…",
                        )
                    raise Retry(defer=2**attempt) from exc
                if analysis_id:
                    await services.events.publish(analysis_id, name, StageState.FAILED, message)
                    if name not in (Stage.INTEL, Stage.TRIAGE):
                        await _finish_failed(services, analysis_id, exc)

        return handler

    return wrap


async def _finish_failed(services: Services, analysis_id: UUID, exc: Exception) -> None:
    budget = isinstance(exc, GreenInkError) and exc.code == ErrorCode.BUDGET_EXCEEDED
    async with services.sessions.begin() as session:
        await repos.set_analysis_status(
            session, analysis_id, AnalysisStatus.PARTIAL if budget else AnalysisStatus.FAILED
        )
    await services.events.publish(
        analysis_id,
        Stage.VERDICT,
        StageState.FAILED,
        "The model budget ran out; showing what was checked so far."
        if budget
        else "This report could not be finished. Try again in a minute.",
    )


# Pipeline


@stage(Stage.INGEST)
async def _ingest(services: Services, key: str, payload: dict[str, Any]) -> None:
    tender_id = UUID(payload["tender_id"])
    analysis_id = _analysis_id(payload)
    async with services.sessions.begin() as session:
        tender = await repos.get_tender(session, tender_id)
        if tender is None:
            raise GreenInkError(ErrorCode.NOT_FOUND, "The tender no longer exists.", retryable=False)
        documents = await repos.tender_documents(session, tender_id)
        if analysis_id:
            await repos.set_analysis_status(session, analysis_id, AnalysisStatus.RUNNING)

    if not documents and tender.source == TenderSource.GEM:
        if analysis_id:
            await services.events.publish(
                analysis_id, Stage.INGEST, StageState.RUNNING, "Downloading the bid from GeM…"
            )
        fetched = await services.gem.fetch(tender)
        for file in fetched.files:
            digest = sha256_hex(file.content)
            blob_key = f"tenders/{digest}{EXTENSIONS.get(file.content_type, '.xlsx')}"
            await services.blobs.put(blob_key, file.content, file.content_type)
            async with services.sessions.begin() as session:
                await repos.add_document(session, tender_id, digest, file.filename, blob_key, file.source_url)
        async with services.sessions() as session:
            documents = await repos.tender_documents(session, tender_id)
        if analysis_id:
            attachments = len(documents) - 1
            extra = (
                f" and {attachments} attachment{'s' if attachments != 1 else ''}" if attachments > 0 else ""
            )
            await services.events.publish(
                analysis_id, Stage.INGEST, StageState.DONE, f"Downloaded the bid document{extra}."
            )
    elif analysis_id:
        await services.events.publish(
            analysis_id, Stage.INGEST, StageState.SKIPPED, "Documents already stored."
        )

    if not documents:
        raise GreenInkError(ErrorCode.NOT_FOUND, "This tender has no documents to read.", retryable=False)
    await _advance(services, tender_id, documents, analysis_id)


async def _advance(
    services: Services, tender_id: UUID, documents: list[repos.StoredDocument], analysis_id: UUID | None
) -> None:
    """Queue the next step for every document; if all are extracted, queue judging."""
    version = services.requirements_version
    pending = [d for d in documents if d.extracted_version != version]
    for stored in pending:
        payload = {
            "document_id": str(stored.document.id),
            "analysis_id": str(analysis_id) if analysis_id else None,
        }
        if stored.document.page_count is None:
            await services.queue.enqueue(JobName.PARSE, stored.document.sha256, payload)
        else:
            await services.queue.enqueue(JobName.EXTRACT, f"{stored.document.sha256}:{version}", payload)
    if not pending:
        await _queue_judging(services, tender_id)


async def _queue_judging(services: Services, tender_id: UUID) -> None:
    async with services.sessions() as session:
        waiting = await repos.analyses_waiting_for(session, tender_id)
    for analysis_id in waiting:
        await services.queue.enqueue(JobName.JUDGE, str(analysis_id), {"analysis_id": str(analysis_id)})


@stage(Stage.PARSE)
async def _parse(services: Services, key: str, payload: dict[str, Any]) -> None:
    analysis_id = _analysis_id(payload)
    async with services.sessions() as session:
        stored = await repos.get_document(session, UUID(payload["document_id"]))
    if stored is None:
        raise GreenInkError(ErrorCode.NOT_FOUND, "The document no longer exists.", retryable=False)
    if stored.document.page_count is None:
        if analysis_id:
            await services.events.publish(
                analysis_id, Stage.PARSE, StageState.RUNNING, f"Reading {stored.document.filename}…"
            )
        pages = await services.parser.parse(
            await services.blobs.get(stored.blob_key), analysis_id=analysis_id
        )
        async with services.sessions.begin() as session:
            await repos.save_pages(
                session,
                stored.document.id,
                [
                    Page(document_id=stored.document.id, page_no=p.page_no, text=p.text, method=p.method)
                    for p in pages
                ],
            )
        if analysis_id:
            scanned = sum(p.method == PageMethod.VISION for p in pages)
            note = f" ({scanned} scanned, read by vision)" if scanned else ""
            await services.events.publish(
                analysis_id, Stage.PARSE, StageState.DONE, f"Read {len(pages)} pages{note}."
            )
    await services.queue.enqueue(
        JobName.EXTRACT, f"{stored.document.sha256}:{services.requirements_version}", payload
    )


@stage(Stage.EXTRACT)
async def _extract(services: Services, key: str, payload: dict[str, Any]) -> None:
    analysis_id = _analysis_id(payload)
    version = services.requirements_version
    async with services.sessions() as session:
        stored = await repos.get_document(session, UUID(payload["document_id"]))
        if stored is None:
            raise GreenInkError(ErrorCode.NOT_FOUND, "The document no longer exists.", retryable=False)
        pages = [
            ParsedPage(page_no=p.page_no, text=p.text, method=p.method)
            for p in await repos.get_pages(session, stored.document.id)
        ]
    if stored.extracted_version != version:
        if analysis_id:
            await services.events.publish(
                analysis_id,
                Stage.EXTRACT,
                StageState.RUNNING,
                f"Finding requirements in {stored.document.filename}…",
            )
        extracted = await services.extractor.extract(stored.document.id, pages, analysis_id=analysis_id)
        checked = services.verifier.verify(extracted, pages)
        verified = sum(r.verified for r in checked)
        async with services.sessions.begin() as session:
            await repos.save_requirements(session, stored.document.id, version, checked)
        if analysis_id:
            await services.events.publish(
                analysis_id,
                Stage.EXTRACT,
                StageState.DONE,
                f"{len(checked)} requirements found in {stored.document.filename}.",
            )
            await services.events.publish(
                analysis_id,
                Stage.VERIFY,
                StageState.DONE,
                f"{len(checked)} requirements found; {verified} verified on their cited page.",
            )
    async with services.sessions() as session:
        documents = await repos.tender_documents(session, stored.document.tender_id)
    if all(d.extracted_version == version for d in documents):
        await _queue_judging(services, stored.document.tender_id)


@stage(Stage.JUDGE)
async def _judge(services: Services, key: str, payload: dict[str, Any]) -> None:
    analysis_id = UUID(key)
    async with services.sessions() as session:
        analysis = await repos.get_analysis(session, analysis_id)
        if analysis is None or analysis.status in (AnalysisStatus.DONE, AnalysisStatus.PARTIAL):
            return
        tender = await repos.get_tender(session, analysis.tender_id)
        owned = await repos.get_company(session, analysis.company_id)
        requirements = await repos.tender_requirements(
            session, analysis.tender_id, analysis.requirements_version
        )
    if tender is None or owned is None:
        raise GreenInkError(ErrorCode.NOT_FOUND, "The tender or company no longer exists.", retryable=False)

    verified = [r for r in requirements if r.verified]
    if not verified:
        async with services.sessions.begin() as session:
            await repos.set_verdict(session, analysis_id, AnalysisStatus.PARTIAL, None, None, [])
        await services.events.publish(
            analysis_id,
            Stage.VERDICT,
            StageState.FAILED,
            "No requirement could be verified against its page, so there is no verdict. "
            "The bid's terms may be in attachments we could not read.",
        )
        return

    await services.events.publish(
        analysis_id,
        Stage.JUDGE,
        StageState.RUNNING,
        f"Checking {len(verified)} requirements against {owned.company.name}…",
    )
    facts = {"Item": tender.title}
    if tender.meta.get("quantity") is not None:
        facts["Total quantity"] = str(tender.meta["quantity"])
    if tender.buyer:
        facts["Buyer"] = tender.buyer
    findings = await services.judge.judge(
        analysis_id, verified, owned.company.profile, tender.closes_at, bid_facts=facts
    )
    outcome = decide(findings)
    risks = sum(f.status != FindingStatus.PASS for f in findings)
    async with services.sessions.begin() as session:
        await repos.save_findings(session, analysis_id, findings)
        await repos.set_verdict(
            session, analysis_id, AnalysisStatus.DONE, outcome.verdict, outcome.reason, outcome.rules
        )
    await services.events.publish(
        analysis_id, Stage.JUDGE, StageState.DONE, f"Checked {len(findings)} requirements: {risks} risks."
    )
    await services.events.publish(analysis_id, Stage.VERDICT, StageState.DONE, outcome.reason)


@stage(Stage.INTEL)
async def _intel(services: Services, key: str, payload: dict[str, Any]) -> None:
    analysis_id = UUID(key)
    if services.intel is None:
        await services.events.publish(
            analysis_id, Stage.INTEL, StageState.SKIPPED, "Price search is not configured."
        )
        return
    async with services.sessions() as session:
        analysis = await repos.get_analysis(session, analysis_id)
        tender = await repos.get_tender(session, analysis.tender_id) if analysis else None
        existing = await repos.price_intel(session, analysis_id)
    if tender is None:
        return
    if existing:
        await services.events.publish(
            analysis_id, Stage.INTEL, StageState.SKIPPED, "Price intel already found."
        )
        return
    await services.events.publish(
        analysis_id, Stage.INTEL, StageState.RUNNING, "Searching past prices with Tavily…"
    )
    intel = await services.intel.prices(analysis_id, tender.title, tender.buyer)
    async with services.sessions.begin() as session:
        await repos.save_price_intel(session, intel)
    await services.events.publish(
        analysis_id, Stage.INTEL, StageState.DONE, f"Found {len(intel.sources)} price sources."
    )


# On-demand work


def triage_key(search_id: str) -> str:
    return f"triage:{search_id}"


@stage(Stage.TRIAGE)
async def _triage(services: Services, key: str, payload: dict[str, Any]) -> None:
    search_id = payload["search_id"]
    async with services.sessions() as session:
        owned = await repos.get_company(session, UUID(payload["company_id"]))
    if owned is None:
        return
    bids = [BidSummary.model_validate(b) for b in payload["bids"]]
    badges = await services.triage.score(bids, owned.company.profile)
    redis_key = triage_key(search_id)
    if badges:
        await services.redis.hset(  # type: ignore[misc]
            redis_key, mapping={ref: badge.model_dump_json() for ref, badge in badges.items()}
        )
    await services.redis.hset(redis_key, "__done__", "1")  # type: ignore[misc]
    await services.redis.expire(redis_key, TRIAGE_TTL_S)
    await services.redis.publish(f"search:{search_id}", json.dumps({"done": True}))


@stage(Stage.VERDICT, report=False)
async def _fix(services: Services, key: str, payload: dict[str, Any]) -> None:
    finding_id = UUID(key)
    analysis_id = UUID(payload["analysis_id"])
    async with services.sessions() as session:
        analysis = await repos.get_analysis(session, analysis_id)
        findings = await repos.findings(session, analysis_id)
        owned = await repos.get_company(session, analysis.company_id) if analysis else None
    finding = next((f for f in findings if f.id == finding_id), None)
    if finding is None or owned is None or finding.fix is not None:
        return
    fix = await services.fixer.draft(finding, owned.company.profile, analysis_id=analysis_id)
    async with services.sessions.begin() as session:
        await repos.set_fix(session, finding_id, fix)


async def _company_from_url(ctx: dict[str, Any], key: str, payload: dict[str, Any]) -> None:
    services = _services(ctx)
    if services.website is None:
        log.warning("company_from_url_unconfigured")
        return
    company_id = UUID(key)
    try:
        profile = await services.website.from_url(payload["url"])
    except GreenInkError as exc:
        log.warning("company_from_url_failed", error=exc.message)
        async with services.sessions() as session:
            owned = await repos.get_company(session, company_id)
        if owned is not None:
            failed = owned.company.profile.model_copy(
                update={"legal_name": f"{owned.company.name} (could not read site)"}
            )
            async with services.sessions.begin() as session:
                await repos.save_company(
                    session,
                    company_id=company_id,
                    name=owned.company.name,
                    profile=failed,
                    source=CompanySource.URL,
                    verified_level=VerifiedLevel.UNVERIFIED,
                    session_id=owned.session_id,
                )
        return
    async with services.sessions() as session:
        owned = await repos.get_company(session, company_id)
    if owned is None:
        return
    async with services.sessions.begin() as session:
        await repos.save_company(
            session,
            company_id=company_id,
            name=profile.legal_name or owned.company.name,
            profile=profile,
            source=CompanySource.URL,
            verified_level=VerifiedLevel.UNVERIFIED,
            session_id=owned.session_id,
        )


async def _company_document(ctx: dict[str, Any], key: str, payload: dict[str, Any]) -> None:
    services = _services(ctx)
    document_id, company_id = UUID(key), UUID(payload["company_id"])
    async with services.sessions() as session:
        owned = await repos.get_company(session, company_id)
        stored = next(
            (d for d in await repos.company_documents(session, company_id) if d.document.id == document_id),
            None,
        )
    if owned is None or stored is None:
        return
    pages = await services.parser.parse(await services.blobs.get(stored.blob_key))
    reading = await services.documents.from_document(owned.company.profile, stored.document.kind, pages)
    async with services.sessions.begin() as session:
        await repos.set_company_document_facts(session, document_id, reading.facts)
        await repos.save_company(
            session,
            company_id=company_id,
            name=owned.company.name,
            profile=reading.profile,
            source=owned.company.source if owned.company.source != CompanySource.URL else CompanySource.DOCS,
            verified_level=VerifiedLevel.PARTIAL,
            session_id=owned.session_id,
        )


HANDLERS: dict[JobName, Handler] = {
    JobName.INGEST: _ingest,
    JobName.PARSE: _parse,
    JobName.EXTRACT: _extract,
    JobName.JUDGE: _judge,
    JobName.INTEL: _intel,
    JobName.TRIAGE: _triage,
    JobName.FIX: _fix,
    JobName.COMPANY_FROM_URL: _company_from_url,
    JobName.COMPANY_DOCUMENT: _company_document,
}


def handlers_for(queue: QueueName) -> dict[JobName, Handler]:
    return {job: handler for job, handler in HANDLERS.items() if JOB_QUEUE[job] == queue}
