"""Every error leaves the API as `{code, message, retryable}`; no stack traces reach clients."""

from typing import Any

import structlog
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from greenink.core.api import ErrorBody
from greenink.core.enums import ErrorCode
from greenink.core.errors import GreenInkError

log = structlog.get_logger()

_DESCRIPTIONS: dict[int, str] = {
    400: "Bad request",
    404: "Not found",
    409: "Conflict",
    413: "Payload too large",
    415: "Unsupported media type",
    422: "Validation error",
    429: "Rate limited or budget exceeded",
    500: "Internal error",
    501: "Not implemented yet",
    503: "Not ready",
}


def error_responses(*statuses: int) -> dict[int | str, dict[str, Any]]:
    """OpenAPI `responses` entries that use the error shape."""
    return {status: {"model": ErrorBody, "description": _DESCRIPTIONS[status]} for status in statuses}


def error_response(code: ErrorCode, message: str, status: int, retryable: bool) -> JSONResponse:
    body = ErrorBody(code=code, message=message, retryable=retryable)
    return JSONResponse(body.model_dump(mode="json"), status_code=status)


async def _greenink_error(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, GreenInkError)
    return error_response(exc.code, exc.message, exc.http_status, exc.retryable)


async def _not_implemented(request: Request, exc: Exception) -> JSONResponse:
    log.info("not_implemented", path=request.url.path, todo=str(exc))
    return error_response(
        ErrorCode.NOT_IMPLEMENTED, "This endpoint is not available yet.", 501, retryable=False
    )


async def _validation_error(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)
    problems = "; ".join(
        f"{'.'.join(str(part) for part in error['loc'])}: {error['msg']}" for error in exc.errors()
    )
    return error_response(ErrorCode.VALIDATION_ERROR, problems or "Invalid request.", 422, False)


async def _http_error(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, StarletteHTTPException)
    code = {404: ErrorCode.NOT_FOUND, 405: ErrorCode.BAD_REQUEST}.get(exc.status_code, ErrorCode.BAD_REQUEST)
    return error_response(code, str(exc.detail), exc.status_code, retryable=False)


async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
    log.exception("unhandled_error", path=request.url.path)
    return error_response(ErrorCode.INTERNAL, "Something went wrong on our side.", 500, True)


def install_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(GreenInkError, _greenink_error)
    app.add_exception_handler(NotImplementedError, _not_implemented)
    app.add_exception_handler(RequestValidationError, _validation_error)
    app.add_exception_handler(StarletteHTTPException, _http_error)
    app.add_exception_handler(Exception, _unhandled)
