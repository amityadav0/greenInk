"""Analyses: one tender judged for one company, streamed as it runs."""

import asyncio
import hashlib
import json
from collections.abc import AsyncIterable
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Header, Request, Response, status
from fastapi.responses import JSONResponse
from fastapi.sse import EventSourceResponse, ServerSentEvent

from greenink.analysis.extract import LLMExtractor
from greenink.core.api import (
    Accepted,
    AnalysisCreate,
    AnalysisReport,
    AnalysisTrace,
    StageStatus,
    TraceTotals,
)
from greenink.core.enums import AnalysisStatus, ErrorCode, FindingStatus, Severity, Stage, StageState
from greenink.core.errors import GreenInkError
from greenink.core.models import CompanyProfile, Finding, Fix, JobEvent
from greenink.db import repos
from greenink.jobs.queue import JobName
from greenink_api.deps import ANALYSIS_LIMIT, FIX_LIMIT, AppState, check_limit, session_id, state
from greenink_api.errors import error_responses

router = APIRouter(prefix="/v1/analyses", tags=["analyses"])

REQUIREMENTS_VERSION = LLMExtractor.version
STREAM_TIMEOUT_S = 240
TERMINAL = frozenset({StageState.DONE, StageState.FAILED, StageState.SKIPPED})
FINISHED = frozenset({AnalysisStatus.DONE, AnalysisStatus.PARTIAL, AnalysisStatus.FAILED})
SEVERITY_ORDER = {Severity.CRITICAL: 0, Severity.HIGH: 1, Severity.MEDIUM: 2, Severity.LOW: 3}


def profile_hash(profile: CompanyProfile) -> str:
    """Part of the analysis cache key: editing the company re-judges."""
    canonical = json.dumps(profile.model_dump(mode="json"), sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical.encode()).hexdigest()


def _status_url(analysis_id: UUID) -> str:
    return f"/v1/analyses/{analysis_id}"


@router.post(
    "",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=Accepted,
    responses=error_responses(404, 422, 429),
    operation_id="createAnalysis",
    summary="Start an analysis, or return the cached one when its key matches",
)
async def create_analysis(request: Request, response: Response, body: AnalysisCreate) -> Accepted:
    session = session_id(request, response)
    app = state(request)
    async with app.sessions() as db:
        tender = await repos.get_tender(db, body.tender_id)
        owned = await repos.get_company(db, body.company_id)
    if tender is None:
        raise GreenInkError(ErrorCode.NOT_FOUND, "That tender was not found.")
    if owned is None or not owned.visible_to(session):
        raise GreenInkError(ErrorCode.NOT_FOUND, "That company was not found.")

    key_hash = profile_hash(owned.company.profile)
    async with app.sessions() as db:
        existing = await repos.find_analysis(db, tender.id, owned.company.id, key_hash, REQUIREMENTS_VERSION)
    if existing is None or existing.status == AnalysisStatus.FAILED:
        await check_limit(request, ANALYSIS_LIMIT)
    async with app.sessions.begin() as db:
        analysis, created = await repos.find_or_create_analysis(
            db, tender.id, owned.company.id, key_hash, REQUIREMENTS_VERSION
        )
        rerun = analysis.status == AnalysisStatus.FAILED
        if rerun:
            await repos.set_analysis_status(db, analysis.id, AnalysisStatus.QUEUED)
    if created or rerun:
        payload = {"tender_id": str(tender.id), "analysis_id": str(analysis.id)}
        await app.queue.enqueue(JobName.INGEST, f"{tender.source.value}:{tender.source_ref}", payload)
        await app.queue.enqueue(JobName.INTEL, str(analysis.id), {"analysis_id": str(analysis.id)})
    return Accepted(
        id=analysis.id,
        status_url=_status_url(analysis.id),
        events_url=f"{_status_url(analysis.id)}/events",
        cached=not created and analysis.status == AnalysisStatus.DONE,
    )


def _sorted(findings: list[Finding]) -> list[Finding]:
    return sorted(
        findings,
        key=lambda f: (f.status == FindingStatus.PASS, SEVERITY_ORDER[f.severity], f.requirement.page_no),
    )


def _stages(events: list[tuple[int, JobEvent]]) -> list[StageStatus]:
    latest: dict[Stage, JobEvent] = {}
    for _, event in events:
        latest[event.stage] = event
    return [StageStatus(stage=s, state=e.state, message=e.message) for s, e in latest.items()]


@router.get(
    "/{analysis_id}",
    response_model=AnalysisReport,
    responses=error_responses(404, 422),
    operation_id="getAnalysis",
    summary="Full report: verdict, findings, price intel, stage states",
)
async def get_analysis(request: Request, analysis_id: UUID) -> AnalysisReport:
    async with state(request).sessions() as db:
        analysis = await repos.get_analysis(db, analysis_id)
        if analysis is None:
            raise GreenInkError(ErrorCode.NOT_FOUND, "That report was not found.")
        tender = await repos.get_tender(db, analysis.tender_id)
        findings = await repos.findings(db, analysis_id)
        intel = await repos.price_intel(db, analysis_id)
        events = await repos.events_after(db, analysis_id)
    assert tender is not None
    return AnalysisReport(
        analysis=analysis,
        tender=tender,
        findings=_sorted(findings),
        price_intel=intel,
        stages=_stages(events),
    )


def _complete(seen: dict[Stage, StageState]) -> bool:
    verdict_done = seen.get(Stage.VERDICT) in (StageState.DONE, StageState.FAILED)
    intel_done = seen.get(Stage.INTEL) in TERMINAL
    failed = any(state == StageState.FAILED for stage, state in seen.items() if stage != Stage.INTEL)
    return (verdict_done and intel_done) or (failed and intel_done)


@router.get(
    "/{analysis_id}/events",
    response_class=EventSourceResponse,
    responses=error_responses(404, 422),
    operation_id="analysisEvents",
    summary="Stage progress; resumes after Last-Event-ID",
)
async def analysis_events(
    request: Request,
    analysis_id: UUID,
    last_event_id: Annotated[str | None, Header()] = None,
) -> AsyncIterable[JobEvent]:
    app = state(request)
    async with app.sessions() as db:
        analysis = await repos.get_analysis(db, analysis_id)
        history = await repos.events_after(db, analysis_id)
    if analysis is None:
        raise GreenInkError(ErrorCode.NOT_FOUND, "That report was not found.")
    after = int(last_event_id) if last_event_id and last_event_id.isdigit() else 0
    seen: dict[Stage, StageState] = {e.stage: e.state for event_id, e in history if event_id <= after}

    stream = app.events.subscribe(analysis_id, after)
    try:
        async with asyncio.timeout(STREAM_TIMEOUT_S):
            async for event_id, event in stream:
                seen[event.stage] = event.state
                yield ServerSentEvent(data=event, id=str(event_id), event="stage")  # type: ignore[misc]
                if _complete(seen) or (
                    analysis.status in FINISHED and not await _more_coming(app, analysis_id)
                ):
                    break
    except TimeoutError:
        pass
    finally:
        await stream.aclose()  # type: ignore[attr-defined]
    yield ServerSentEvent(data={"analysis_id": str(analysis_id)}, event="done")  # type: ignore[misc]


async def _more_coming(app: AppState, analysis_id: UUID) -> bool:
    """A finished analysis may still be waiting for its price intel."""
    async with app.sessions() as db:
        events = await repos.events_after(db, analysis_id)
    return not any(e.stage == Stage.INTEL and e.state in TERMINAL for _, e in events)


@router.get(
    "/{analysis_id}/trace",
    response_model=AnalysisTrace,
    responses=error_responses(404, 422),
    operation_id="getAnalysisTrace",
    summary="Model Trace: model, tokens, $ and ms per call",
)
async def get_analysis_trace(request: Request, analysis_id: UUID) -> AnalysisTrace:
    async with state(request).sessions() as db:
        analysis = await repos.get_analysis(db, analysis_id)
        if analysis is None:
            raise GreenInkError(ErrorCode.NOT_FOUND, "That report was not found.")
        calls = await repos.llm_calls(db, analysis_id)
    return AnalysisTrace(
        analysis_id=analysis_id,
        status=analysis.status,
        calls=calls,
        totals=TraceTotals(
            tokens_in=sum(c.tokens_in for c in calls),
            tokens_out=sum(c.tokens_out for c in calls),
            cost_usd=round(sum(c.cost_usd for c in calls), 6),
            latency_ms=sum(c.latency_ms for c in calls),
        ),
    )


@router.post(
    "/{analysis_id}/findings/{finding_id}/fix",
    response_model=Fix,
    responses={
        202: {"model": Accepted, "description": "Drafting; poll this endpoint until it returns 200"},
        **error_responses(404, 422, 429),
    },
    operation_id="draftFix",
    summary="The drafted fix: 200 when ready, else 202 while it is drafted",
)
async def draft_fix(request: Request, analysis_id: UUID, finding_id: UUID) -> Fix | JSONResponse:
    app = state(request)
    async with app.sessions() as db:
        finding = next((f for f in await repos.findings(db, analysis_id) if f.id == finding_id), None)
    if finding is None:
        raise GreenInkError(ErrorCode.NOT_FOUND, "That finding was not found.")
    if finding.fix is not None:
        return finding.fix
    await check_limit(request, FIX_LIMIT)
    await app.queue.enqueue(JobName.FIX, str(finding_id), {"analysis_id": str(analysis_id)})
    accepted = Accepted(id=finding_id, status_url=f"/v1/analyses/{analysis_id}/findings/{finding_id}/fix")
    return JSONResponse(accepted.model_dump(mode="json"), status_code=status.HTTP_202_ACCEPTED)


@router.get(
    "/{analysis_id}/export.pdf",
    response_class=Response,
    responses={
        200: {"content": {"application/pdf": {"schema": {"type": "string", "format": "binary"}}}},
        **error_responses(404, 422, 501),
    },
    operation_id="exportAnalysisPdf",
    summary="PDF report (P1)",
)
async def export_analysis_pdf(analysis_id: UUID) -> Response:
    # TODO(lane-B): render the report as PDF (P1; the web app offers print-to-PDF meanwhile).
    raise NotImplementedError("TODO(lane-B): render the report as PDF")
