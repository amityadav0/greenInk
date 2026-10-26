"""Tender metadata, page text for the viewer, and tender upload."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Path, Query, Request, status

from greenink.core.api import Accepted, PageText, TenderDetail
from greenink_api.errors import error_responses
from greenink_api.routes.stubs import PDF_FILE, multipart_body

router = APIRouter(prefix="/v1/tenders", tags=["tenders"])


@router.post(
    "/upload",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=Accepted,
    responses=error_responses(413, 415, 422, 429, 501),
    operation_id="uploadTender",
    summary="Upload any tender PDF (non-GeM portals)",
    openapi_extra=multipart_body(file=PDF_FILE),
)
async def upload_tender(request: Request) -> Accepted:
    raise NotImplementedError("TODO(lane-B): validate bytes, store blob, enqueue ingest")


@router.get(
    "/{tender_id}",
    response_model=TenderDetail,
    responses=error_responses(404, 422, 501),
    operation_id="getTender",
)
async def get_tender(tender_id: UUID) -> TenderDetail:
    raise NotImplementedError("TODO(lane-B): tender + signed document URLs")


@router.get(
    "/{tender_id}/pages/{page_no}",
    response_model=PageText,
    responses=error_responses(404, 422, 501),
    operation_id="getTenderPage",
    summary="Page text for the viewer's highlight",
)
async def get_tender_page(
    tender_id: UUID,
    page_no: Annotated[int, Path(ge=1)],
    document_id: Annotated[UUID | None, Query(description="Defaults to the tender's main document.")] = None,
) -> PageText:
    raise NotImplementedError("TODO(lane-B): page text from `pages`")
