"""S3-compatible blob store: MinIO locally, Cloudflare R2 in production."""

from pydantic import SecretStr


class S3BlobStore:
    def __init__(
        self, endpoint_url: str, bucket: str, access_key_id: SecretStr, secret_access_key: SecretStr
    ) -> None:
        self._endpoint_url = endpoint_url
        self._bucket = bucket
        self._access_key_id = access_key_id
        self._secret_access_key = secret_access_key

    async def put(self, key: str, data: bytes, content_type: str) -> None:
        raise NotImplementedError("TODO(lane-C): boto3 put_object, off the event loop")

    async def get(self, key: str) -> bytes:
        raise NotImplementedError("TODO(lane-C): boto3 get_object")

    async def signed_url(self, key: str, expires_s: int = 300) -> str:
        raise NotImplementedError("TODO(lane-C): boto3 generate_presigned_url")
