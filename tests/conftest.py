from collections.abc import Iterator
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from greenink.core.settings import Settings, get_settings
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


@pytest.fixture
def scratch_database_url() -> Iterator[str]:
    url = make_url(get_settings().database_url)
    admin = create_engine(url.set(drivername="postgresql+psycopg"), isolation_level="AUTOCOMMIT")
    try:
        with admin.connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception:
        pytest.skip("Postgres unreachable at DATABASE_URL")
    name = f"greenink_test_{uuid4().hex[:12]}"
    with admin.connect() as connection:
        connection.execute(text(f'CREATE DATABASE "{name}"'))
    try:
        yield url.set(database=name).render_as_string(hide_password=False)
    finally:
        with admin.connect() as connection:
            connection.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        admin.dispose()
