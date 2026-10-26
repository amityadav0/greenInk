"""Product search over live tenders, with triage badges streamed in."""

from collections.abc import AsyncIterable
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from fastapi.sse import EventSourceResponse

from greenink.core.api import SearchBadgeEvent, SearchResponse
from greenink_api.errors import error_responses
from greenink_api.routes.stubs import unimplemented_stream

router = APIRouter(prefix="/v1/search", tags=["search"])


@router.get(
    "",
    response_model=SearchResponse,
    responses=error_responses(422, 429, 500, 501),
    operation_id="search",
    summary="Search live bids; cached 30 minutes",
)
async def search(
    q: Annotated[str, Query(min_length=2, max_length=200, description="What the company sells.")],
    company_id: Annotated[UUID | None, Query(description="Company to triage for.")] = None,
) -> SearchResponse:
    raise NotImplementedError("TODO(lane-B): search via sources + Redis cache; enqueue triage")


@router.get(
    "/{search_id}/events",
    response_class=EventSourceResponse,
    responses=error_responses(404, 422, 501),
    operation_id="searchEvents",
    summary="Triage badge updates (event: badge), then event: done",
    dependencies=[Depends(unimplemented_stream)],
)
async def search_events(search_id: UUID) -> AsyncIterable[SearchBadgeEvent]:
    raise NotImplementedError("TODO(lane-B): relay triage badges")
    yield  # pragma: no cover
