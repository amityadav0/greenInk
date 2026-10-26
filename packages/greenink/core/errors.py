"""The one error type. The API turns it into `{code, message, retryable}`."""

from greenink.core.enums import ErrorCode

_HTTP_STATUS: dict[ErrorCode, int] = {
    ErrorCode.BAD_REQUEST: 400,
    ErrorCode.VALIDATION_ERROR: 422,
    ErrorCode.NOT_FOUND: 404,
    ErrorCode.CONFLICT: 409,
    ErrorCode.PAYLOAD_TOO_LARGE: 413,
    ErrorCode.UNSUPPORTED_MEDIA_TYPE: 415,
    ErrorCode.RATE_LIMITED: 429,
    ErrorCode.BUDGET_EXCEEDED: 429,
    ErrorCode.NOT_IMPLEMENTED: 501,
    ErrorCode.UPSTREAM_UNAVAILABLE: 502,
    ErrorCode.NOT_READY: 503,
    ErrorCode.INTERNAL: 500,
}

_RETRYABLE: frozenset[ErrorCode] = frozenset(
    {ErrorCode.RATE_LIMITED, ErrorCode.UPSTREAM_UNAVAILABLE, ErrorCode.NOT_READY, ErrorCode.INTERNAL}
)


class GreenInkError(Exception):
    """An error with a user-facing message. Never put secrets or raw upstream bodies in it."""

    def __init__(self, code: ErrorCode, message: str, *, retryable: bool | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = code in _RETRYABLE if retryable is None else retryable

    @property
    def http_status(self) -> int:
        return _HTTP_STATUS[self.code]
