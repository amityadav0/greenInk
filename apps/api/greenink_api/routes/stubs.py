"""Shared helpers for routes that are in the contract but not built yet."""

from typing import Any

from greenink.core.enums import CompanyDocumentKind


def unimplemented_stream() -> None:
    """Dependency for SSE routes not built yet.

    An SSE body only starts after the response has begun, so raising inside it would send
    an empty `200`. Dependencies run first, so this one yields a proper `501`.
    """
    raise NotImplementedError("TODO(lane-B): SSE stream")


def multipart_body(**fields: dict[str, Any]) -> dict[str, Any]:
    """`openapi_extra` for a multipart upload. Routes parse the form themselves."""
    return {
        "requestBody": {
            "required": True,
            "content": {
                "multipart/form-data": {
                    "schema": {
                        "type": "object",
                        "required": list(fields),
                        "properties": fields,
                    }
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
