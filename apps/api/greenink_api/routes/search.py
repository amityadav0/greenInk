"""Product search over live tenders, with triage badges streamed in."""

import asyncio
import json
from collections.abc import AsyncIterable
from typing import Annotated
from uuid import NAMESPACE_URL, UUID, uuid5

from fastapi import APIRouter, Query, Request, Response
from fastapi.sse import EventSourceResponse, ServerSentEvent

from greenink.core.api import SearchBadgeEvent, SearchResponse
from greenink.core.enums import ErrorCode
from greenink.core.errors import GreenInkError
from greenink.core.models import BidSummary, Tender, TriageBadge
from greenink.db import repos
from greenink.db.seed import DEMO_COMPANY_ID
from greenink.jobs.queue import JobName
from greenink_api.deps import SEARCH_LIMIT, check_limit, session_id, state
from greenink_api.errors import error_responses

router = APIRouter(prefix="/v1/search", tags=["search"])

DONE = "__done__"
STREAM_TIMEOUT_S = 90
POLL_S = 0.5


def normalise(query: str) -> str:
    return " ".join(query.lower().split())


def triage_key(search_id: UUID) -> str:
    return f"triage:{search_id}"


async def _badges(request: Request, search_id: UUID) -> tuple[dict[str, TriageBadge], bool]:
    raw: dict[bytes, bytes] = await state(request).redis.hgetall(triage_key(search_id))  # type: ignore[misc]
    done = DONE.encode() in raw
    badges = {k.decode(): TriageBadge.model_validate_json(v) for k, v in raw.items() if k.decode() != DONE}
    return badges, done


@router.get(
    "",
    response_model=SearchResponse,
    responses=error_responses(422, 429, 500),
    operation_id="search",
    summary="Search live bids; cached 30 minutes",
)
async def search(
    request: Request,
    response: Response,
    q: Annotated[str, Query(min_length=2, max_length=200, description="What the company sells.")],
    company_id: Annotated[UUID | None, Query(description="Company to triage for.")] = None,
) -> SearchResponse:
    app = state(request)
    session = session_id(request, response)
    query = normalise(q)
    company_id = company_id or DEMO_COMPANY_ID
    async with app.sessions() as db:
        owned = await repos.get_company(db, company_id)
    if owned is None or not owned.visible_to(session):
        raise GreenInkError(ErrorCode.NOT_FOUND, "That company was not found.")

    cache_key = f"search:gem:{query}"
    cached_raw = await app.redis.get(cache_key)
    if cached_raw:
        tenders = [Tender.model_validate(t) for t in json.loads(cached_raw)]
    else:
        await check_limit(request, SEARCH_LIMIT)
        tenders = await app.gem.search(query)
        async with app.sessions.begin() as db:
            await repos.upsert_tenders(db, tenders)
        await app.redis.set(
            cache_key,
            json.dumps([t.model_dump(mode="json") for t in tenders]),
            ex=app.sources.adapters.gem.search_cache_ttl_s,
        )

    search_id = uuid5(NAMESPACE_URL, f"greenink:search:{query}:{company_id}")
    badges, done = await _badges(request, search_id)
    results = [
        BidSummary(
            tender_id=t.id,
            source=t.source,
            source_ref=t.source_ref,
            title=t.title,
            buyer=t.buyer,
            quantity=t.meta.get("quantity"),
            closes_at=t.closes_at,
            value_inr=t.value_inr,
            official_url=t.official_url,
            badge=badges.get(t.source_ref),
        )
        for t in tenders
    ]
    if results and not done:
        await app.queue.enqueue(
            JobName.TRIAGE,
            str(search_id),
            {
                "search_id": str(search_id),
                "company_id": str(company_id),
                "bids": [r.model_dump(mode="json", exclude={"badge"}) for r in results],
            },
        )
    return SearchResponse(
        search_id=search_id,
        query=query,
        company_id=company_id,
        cached=cached_raw is not None,
        results=results,
        events_url=f"/v1/search/{search_id}/events",
    )


@router.get(
    "/{search_id}/events",
    response_class=EventSourceResponse,
    responses=error_responses(422),
    operation_id="searchEvents",
    summary="Triage badge updates (event: badge), then event: done",
)
async def search_events(request: Request, search_id: UUID) -> AsyncIterable[SearchBadgeEvent]:
    sent: set[str] = set()
    for _ in range(int(STREAM_TIMEOUT_S / POLL_S)):
        if await request.is_disconnected():
            return
        badges, done = await _badges(request, search_id)
        for ref, badge in badges.items():
            if ref not in sent:
                sent.add(ref)
                yield ServerSentEvent(  # type: ignore[misc]
                    data=SearchBadgeEvent(search_id=search_id, source_ref=ref, badge=badge), event="badge"
                )
        if done:
            break
        await asyncio.sleep(POLL_S)
    yield ServerSentEvent(data={"search_id": str(search_id)}, event="done")  # type: ignore[misc]
