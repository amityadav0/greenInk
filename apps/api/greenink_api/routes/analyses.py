"""Analyses: one tender judged for one company, streamed as it runs."""

from collections.abc import AsyncIterable
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, status
from fastapi.responses import Response
from fastapi.sse import EventSourceResponse

from greenink.core.api import Accepted, AnalysisCreate, AnalysisReport, AnalysisTrace
from greenink.core.models import Fix, JobEvent
from greenink_api.errors import error_responses
from greenink_api.routes.stubs import unimplemented_stream

router = APIRouter(prefix="/v1/analyses", tags=["analyses"])


@router.post(
    "",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=Accepted,
    responses=error_responses(404, 422, 429, 501),
    operation_id="createAnalysis",
    summary="Start an analysis, or return the cached one when its key matches",
)
async def create_analysis(body: AnalysisCreate) -> Accepted:
    raise NotImplementedError("TODO(lane-B): cache-key lookup, else create + enqueue ingest")


@router.get(
    "/{analysis_id}",
    response_model=AnalysisReport,
    responses=error_responses(404, 422, 501),
    operation_id="getAnalysis",
    summary="Full report: verdict, findings, price intel, stage states",
)
async def get_analysis(analysis_id: UUID) -> AnalysisReport:
    raise NotImplementedError("TODO(lane-B): assemble the report")


@router.get(
    "/{analysis_id}/events",
    response_class=EventSourceResponse,
    responses=error_responses(404, 422, 501),
    operation_id="analysisEvents",
    summary="Stage progress; resumes after Last-Event-ID",
    dependencies=[Depends(unimplemented_stream)],
)
async def analysis_events(
    analysis_id: UUID,
    last_event_id: Annotated[str | None, Header()] = None,
) -> AsyncIterable[JobEvent]:
    raise NotImplementedError("TODO(lane-B): replay job_events, then relay analysis:{id}")
    yield  # pragma: no cover


@router.get(
    "/{analysis_id}/trace",
    response_model=AnalysisTrace,
    responses=error_responses(404, 422, 501),
    operation_id="getAnalysisTrace",
    summary="Model Trace: model, tokens, $ and ms per call",
)
async def get_analysis_trace(analysis_id: UUID) -> AnalysisTrace:
    raise NotImplementedError("TODO(lane-B): llm_calls for this analysis")


@router.post(
    "/{analysis_id}/findings/{finding_id}/fix",
    response_model=Fix,
    responses={
        202: {"model": Accepted, "description": "Drafting; the fix arrives on the events stream"},
        **error_responses(404, 422, 429, 501),
    },
    operation_id="draftFix",
    summary="The drafted fix: 200 when cached, else 202 while it is drafted",
)
async def draft_fix(analysis_id: UUID, finding_id: UUID) -> Fix:
    raise NotImplementedError("TODO(lane-B): cached fix, else enqueue the fix task")


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
    raise NotImplementedError("TODO(lane-B): render the report as PDF")
