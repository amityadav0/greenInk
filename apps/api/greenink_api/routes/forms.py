"""Multipart upload helpers and their OpenAPI descriptions."""

from typing import Any

from fastapi import Request
from starlette.datastructures import UploadFile

from greenink.core.enums import CompanyDocumentKind, ErrorCode
from greenink.core.errors import GreenInkError


def multipart_body(**fields: dict[str, Any]) -> dict[str, Any]:
    """`openapi_extra` for a multipart upload; routes parse the form with `read_upload`."""
    return {
        "requestBody": {
            "required": True,
            "content": {
                "multipart/form-data": {
                    "schema": {"type": "object", "required": list(fields), "properties": fields}
                }
            },
        }
    }


PDF_FILE = {"type": "string", "format": "binary", "description": "PDF, at most 25 MB."}
DOCUMENT_FILE = {
    "type": "string",
    "format": "binary",
    "description": "PDF, PNG or JPEG, at most 25 MB. Type is checked from the bytes.",
}
DOCUMENT_KIND = {"type": "string", "enum": [kind.value for kind in CompanyDocumentKind]}


async def read_upload(request: Request, max_bytes: int) -> tuple[str, bytes, dict[str, str]]:
    """The `file` field's name and bytes (read at most max_bytes + 1), plus the text fields."""
    form = await request.form(max_files=1, max_fields=10)
    try:
        upload = form.get("file")
        if not isinstance(upload, UploadFile):
            raise GreenInkError(ErrorCode.VALIDATION_ERROR, "Attach the file in a field named 'file'.")
        data = await upload.read(max_bytes + 1)
        if len(data) > max_bytes:
            raise GreenInkError(
                ErrorCode.PAYLOAD_TOO_LARGE, f"The file is over {max_bytes // (1024 * 1024)} MB."
            )
        fields = {k: v for k, v in form.items() if isinstance(v, str)}
        return (upload.filename or "upload").rsplit("/", 1)[-1][:200], data, fields
    finally:
        await form.close()
