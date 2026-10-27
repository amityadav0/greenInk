"""Companies: the shared demo company plus the ones a session creates."""

from urllib.parse import urlparse
from uuid import UUID

from fastapi import APIRouter, Request, Response, status

from greenink.core.api import Accepted, CompanyCreate, CompanyFromUrl
from greenink.core.enums import CompanyDocumentKind, CompanySource, ErrorCode, VerifiedLevel
from greenink.core.errors import GreenInkError
from greenink.core.ids import new_id, sha256_hex
from greenink.core.models import Company, CompanyProfile
from greenink.db import repos
from greenink.docs.parse import sniff
from greenink.jobs.queue import JobName
from greenink_api.deps import UPLOAD_LIMIT, check_limit, session_id, state
from greenink_api.errors import error_responses
from greenink_api.routes.forms import DOCUMENT_FILE, DOCUMENT_KIND, multipart_body, read_upload

router = APIRouter(prefix="/v1/companies", tags=["companies"])

CONTENT_TYPES = {"pdf": "application/pdf", "png": "image/png", "jpeg": "image/jpeg"}


@router.get(
    "",
    response_model=list[Company],
    operation_id="listCompanies",
    summary="The demo company and this session's companies",
)
async def list_companies(request: Request, response: Response) -> list[Company]:
    session = session_id(request, response)
    async with state(request).sessions() as db:
        return await repos.list_companies(db, session)


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=Company,
    responses=error_responses(422, 429),
    operation_id="createCompany",
    summary="Create a company from a manual profile",
)
async def create_company(request: Request, response: Response, body: CompanyCreate) -> Company:
    session = session_id(request, response)
    await check_limit(request, UPLOAD_LIMIT)
    async with state(request).sessions.begin() as db:
        return await repos.save_company(
            db,
            company_id=new_id(),
            name=body.name,
            profile=body.profile,
            source=CompanySource.DOCS,
            verified_level=VerifiedLevel.UNVERIFIED,
            session_id=session,
        )


@router.post(
    "/from-url",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=Accepted,
    responses=error_responses(422, 429),
    operation_id="createCompanyFromUrl",
    summary="Draft a company from its website (Tavily); marked unverified",
)
async def create_company_from_url(request: Request, response: Response, body: CompanyFromUrl) -> Accepted:
    session = session_id(request, response)
    await check_limit(request, UPLOAD_LIMIT)
    app = state(request)
    host = urlparse(str(body.url)).hostname or "Company"
    company_id = new_id()
    async with app.sessions.begin() as db:
        await repos.save_company(
            db,
            company_id=company_id,
            name=host,
            profile=CompanyProfile(legal_name=host, website=body.url),
            source=CompanySource.URL,
            verified_level=VerifiedLevel.UNVERIFIED,
            session_id=session,
        )
    await app.queue.enqueue(JobName.COMPANY_FROM_URL, str(company_id), {"url": str(body.url)})
    return Accepted(id=company_id, status_url="/v1/companies")


@router.post(
    "/{company_id}/documents",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=Accepted,
    responses=error_responses(400, 404, 413, 415, 422, 429),
    operation_id="uploadCompanyDocument",
    summary="Upload a document to the company's vault",
    openapi_extra=multipart_body(file=DOCUMENT_FILE, kind=DOCUMENT_KIND),
)
async def upload_company_document(request: Request, response: Response, company_id: UUID) -> Accepted:
    session = session_id(request, response)
    app = state(request)
    async with app.sessions() as db:
        owned = await repos.get_company(db, company_id)
    if owned is None or not owned.visible_to(session):
        raise GreenInkError(ErrorCode.NOT_FOUND, "That company was not found.")
    if owned.company.read_only:
        raise GreenInkError(
            ErrorCode.BAD_REQUEST, "The demo company is read-only; create your own company first."
        )
    await check_limit(request, UPLOAD_LIMIT)
    filename, data, fields = await read_upload(request, app.sources.adapters.upload.max_bytes)
    kind_value = fields.get("kind", CompanyDocumentKind.OTHER.value)
    try:
        kind = CompanyDocumentKind(kind_value)
    except ValueError:
        raise GreenInkError(ErrorCode.VALIDATION_ERROR, f"Unknown document kind {kind_value!r}.") from None
    detected = sniff(data)
    if detected not in CONTENT_TYPES:
        raise GreenInkError(ErrorCode.UNSUPPORTED_MEDIA_TYPE, "Upload a PDF, PNG or JPEG.")
    blob_key = f"companies/{company_id}/{sha256_hex(data)}.{detected}"
    await app.blobs.put(blob_key, data, CONTENT_TYPES[detected])
    async with app.sessions.begin() as db:
        document = await repos.add_company_document(db, company_id, kind, filename, blob_key)
    await app.queue.enqueue(JobName.COMPANY_DOCUMENT, str(document.id), {"company_id": str(company_id)})
    return Accepted(id=document.id, status_url="/v1/companies")
