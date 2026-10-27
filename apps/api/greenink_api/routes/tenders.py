"""Tender metadata, page text for the viewer, the PDF itself, and tender upload."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Path, Query, Request, status
from fastapi.responses import Response

from greenink.core.api import Accepted, PageText, TenderDetail, TenderDocumentOut
from greenink.core.enums import ErrorCode, TenderSource
from greenink.core.errors import GreenInkError
from greenink.core.ids import sha256_hex, tender_id
from greenink.core.models import Tender
from greenink.db import repos
from greenink.sources.upload import check_upload
from greenink_api.deps import UPLOAD_LIMIT, check_limit, state
from greenink_api.errors import error_responses
from greenink_api.routes.forms import PDF_FILE, multipart_body, read_upload

router = APIRouter(prefix="/v1/tenders", tags=["tenders"])


@router.post(
    "/upload",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=Accepted,
    responses=error_responses(413, 415, 422, 429),
    operation_id="uploadTender",
    summary="Upload any tender PDF (non-GeM portals)",
    openapi_extra=multipart_body(file=PDF_FILE),
)
async def upload_tender(request: Request) -> Accepted:
    app = state(request)
    await check_limit(request, UPLOAD_LIMIT)
    max_bytes = app.sources.adapters.upload.max_bytes
    filename, data, _ = await read_upload(request, max_bytes)
    check_upload(data, max_bytes)
    digest = sha256_hex(data)
    blob_key = f"tenders/{digest}.pdf"
    await app.blobs.put(blob_key, data, "application/pdf")
    tender = Tender(
        id=tender_id(TenderSource.UPLOAD.value, digest),
        source=TenderSource.UPLOAD,
        source_ref=digest[:16],
        title=filename.removesuffix(".pdf")[:200] or "Uploaded tender",
        meta={"filename": filename},
    )
    async with app.sessions.begin() as db:
        await repos.upsert_tenders(db, [tender])
        await repos.add_document(db, tender.id, digest, filename, blob_key)
    return Accepted(id=tender.id, status_url=f"/v1/tenders/{tender.id}")


@router.get(
    "/{tender_id}",
    response_model=TenderDetail,
    responses=error_responses(404, 422),
    operation_id="getTender",
)
async def get_tender(request: Request, tender_id: UUID) -> TenderDetail:
    async with state(request).sessions() as db:
        tender = await repos.get_tender(db, tender_id)
        documents = await repos.tender_documents(db, tender_id)
    if tender is None:
        raise GreenInkError(ErrorCode.NOT_FOUND, "That tender was not found.")
    return TenderDetail(
        tender=tender,
        documents=[
            TenderDocumentOut(
                id=d.document.id,
                sha256=d.document.sha256,
                filename=d.document.filename,
                page_count=d.document.page_count,
                download_url=f"/v1/tenders/{tender_id}/documents/{d.document.id}/file",
            )
            for d in documents
        ],
    )


@router.get(
    "/{tender_id}/documents/{document_id}/file",
    response_class=Response,
    responses={
        200: {
            "content": {
                "application/pdf": {"schema": {"type": "string", "format": "binary"}},
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": {
                    "schema": {"type": "string", "format": "binary"}
                },
            },
            "description": "The stored document, for the PDF viewer",
        },
        **error_responses(404, 422),
    },
    operation_id="getTenderDocumentFile",
    summary="The document's bytes, served same-origin for the PDF viewer",
)
async def get_tender_document_file(request: Request, tender_id: UUID, document_id: UUID) -> Response:
    app = state(request)
    async with app.sessions() as db:
        stored = await repos.get_document(db, document_id)
    if stored is None or stored.document.tender_id != tender_id:
        raise GreenInkError(ErrorCode.NOT_FOUND, "That document was not found.")
    data = await app.blobs.get(stored.blob_key)
    media = "application/pdf" if data.startswith(b"%PDF") else "application/octet-stream"
    return Response(
        data,
        media_type=media,
        headers={
            "Cache-Control": "private, max-age=86400, immutable",
            "Content-Disposition": f'inline; filename="{stored.document.filename}"',
        },
    )


@router.get(
    "/{tender_id}/pages/{page_no}",
    response_model=PageText,
    responses=error_responses(404, 422),
    operation_id="getTenderPage",
    summary="Page text for the viewer's highlight",
)
async def get_tender_page(
    request: Request,
    tender_id: UUID,
    page_no: Annotated[int, Path(ge=1)],
    document_id: Annotated[UUID | None, Query(description="Defaults to the tender's main document.")] = None,
) -> PageText:
    async with state(request).sessions() as db:
        documents = await repos.tender_documents(db, tender_id)
        chosen = next((d for d in documents if document_id is None or d.document.id == document_id), None)
        page = await repos.get_page(db, chosen.document.id, page_no) if chosen else None
    if page is None:
        raise GreenInkError(ErrorCode.NOT_FOUND, "That page has not been read yet.")
    return PageText(document_id=page.document_id, page_no=page.page_no, text=page.text, method=page.method)
