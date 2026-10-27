"""Identifiers and content hashes."""

import hashlib
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5


def new_id() -> UUID:
    return uuid4()


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def tender_id(source: str, source_ref: str) -> UUID:
    """Deterministic, so the same bid always has the same id."""
    return uuid5(NAMESPACE_URL, f"greenink:tender:{source}:{source_ref}")
