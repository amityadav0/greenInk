from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from greenink.core.settings import Settings
from greenink_api.main import create_app

REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def client() -> Iterator[TestClient]:
    settings = Settings(
        database_url="postgresql+psycopg://nobody:nobody@127.0.0.1:1/none",
        redis_url="redis://127.0.0.1:1/0",
    )
    with TestClient(create_app(settings), raise_server_exceptions=False) as test_client:
        yield test_client
