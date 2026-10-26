"""Port of the `storage` module: blobs such as tender PDFs and company documents."""

from typing import Protocol


class BlobStore(Protocol):
    async def put(self, key: str, data: bytes, content_type: str) -> None: ...

    async def get(self, key: str) -> bytes: ...

    async def signed_url(self, key: str, expires_s: int = 300) -> str:
        """Short-lived URL for the browser; blobs are never public."""
        ...
