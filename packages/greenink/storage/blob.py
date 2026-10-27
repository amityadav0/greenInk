"""S3-compatible blob store: MinIO locally, any S3 bucket (R2, Railway, Nebius) in production."""

import asyncio
from typing import Any

import boto3
import structlog
from botocore.config import Config
from botocore.exceptions import ClientError
from pydantic import SecretStr

from greenink.core.enums import ErrorCode
from greenink.core.errors import GreenInkError

log = structlog.get_logger()


class S3BlobStore:
    def __init__(
        self,
        endpoint_url: str,
        bucket: str,
        access_key_id: SecretStr,
        secret_access_key: SecretStr,
        addressing_style: str = "path",
    ) -> None:
        self._bucket = bucket
        self._client: Any = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            aws_access_key_id=access_key_id.get_secret_value(),
            aws_secret_access_key=secret_access_key.get_secret_value(),
            region_name="auto",
            config=Config(
                signature_version="s3v4",
                retries={"max_attempts": 3, "mode": "standard"},
                s3={"addressing_style": addressing_style},
            ),
        )

    async def ensure_bucket(self) -> None:
        """Create the bucket locally (MinIO). Hosted buckets are created in their console, and
        the credentials may not allow creating or even listing buckets, so failures only log."""

        def create() -> None:
            try:
                self._client.head_bucket(Bucket=self._bucket)
            except ClientError as exc:
                if exc.response.get("Error", {}).get("Code") not in ("404", "NoSuchBucket"):
                    log.warning("bucket_check_failed", bucket=self._bucket, error=str(exc))
                    return
                try:
                    self._client.create_bucket(Bucket=self._bucket)
                except ClientError as create_exc:
                    log.warning("bucket_create_failed", bucket=self._bucket, error=str(create_exc))

        await asyncio.to_thread(create)

    async def put(self, key: str, data: bytes, content_type: str) -> None:
        await asyncio.to_thread(
            self._client.put_object, Bucket=self._bucket, Key=key, Body=data, ContentType=content_type
        )

    async def get(self, key: str) -> bytes:
        def read() -> bytes:
            try:
                body: bytes = self._client.get_object(Bucket=self._bucket, Key=key)["Body"].read()
            except ClientError as exc:
                raise GreenInkError(ErrorCode.NOT_FOUND, "The stored file is missing.") from exc
            return body

        return await asyncio.to_thread(read)

    async def signed_url(self, key: str, expires_s: int = 300) -> str:
        url: str = await asyncio.to_thread(
            self._client.generate_presigned_url,
            "get_object",
            Params={"Bucket": self._bucket, "Key": key},
            ExpiresIn=expires_s,
        )
        return url


class MemoryBlobStore:
    """For tests and local scripts."""

    def __init__(self) -> None:
        self.blobs: dict[str, tuple[bytes, str]] = {}

    async def put(self, key: str, data: bytes, content_type: str) -> None:
        self.blobs[key] = (data, content_type)

    async def get(self, key: str) -> bytes:
        if key not in self.blobs:
            raise GreenInkError(ErrorCode.NOT_FOUND, "The stored file is missing.")
        return self.blobs[key][0]

    async def signed_url(self, key: str, expires_s: int = 300) -> str:
        return f"memory://{key}"
