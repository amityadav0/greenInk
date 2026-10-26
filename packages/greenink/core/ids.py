"""Identifiers and content hashes."""

import hashlib
from uuid import UUID, uuid4


def new_id() -> UUID:
    return uuid4()


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
