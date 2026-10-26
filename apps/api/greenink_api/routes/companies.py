"""Companies: the shared demo company plus the ones a session creates."""

from uuid import UUID

from fastapi import APIRouter, Request, status

from greenink.core.api import Accepted, CompanyCreate, CompanyFromUrl
from greenink.core.models import Company
from greenink_api.errors import error_responses
from greenink_api.routes.stubs import DOCUMENT_FILE, DOCUMENT_KIND, multipart_body

router = APIRouter(prefix="/v1/companies", tags=["companies"])


@router.get(
    "",
    response_model=list[Company],
    responses=error_responses(501),
    operation_id="listCompanies",
    summary="The demo company and this session's companies",
)
async def list_companies() -> list[Company]:
    raise NotImplementedError("TODO(lane-B): demo + session companies")


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=Company,
    responses=error_responses(422, 429, 501),
    operation_id="createCompany",
    summary="Create a company from a manual profile",
)
async def create_company(body: CompanyCreate) -> Company:
    raise NotImplementedError("TODO(lane-B): store company for this session")


@router.post(
    "/from-url",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=Accepted,
    responses=error_responses(422, 429, 501),
    operation_id="createCompanyFromUrl",
    summary="Draft a company from its website (Tavily); marked unverified",
)
async def create_company_from_url(body: CompanyFromUrl) -> Accepted:
    raise NotImplementedError("TODO(lane-B): enqueue profile_url job")


@router.post(
    "/{company_id}/documents",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=Accepted,
    responses=error_responses(404, 413, 415, 422, 429, 501),
    operation_id="uploadCompanyDocument",
    summary="Upload a document to the company's vault",
    openapi_extra=multipart_body(file=DOCUMENT_FILE, kind=DOCUMENT_KIND),
)
async def upload_company_document(company_id: UUID, request: Request) -> Accepted:
    raise NotImplementedError("TODO(lane-B): validate bytes, store blob, enqueue extraction")
