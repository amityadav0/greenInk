"""The initial migration creates exactly the tables in greenink.db.models.

Needs Postgres (`docker compose up postgres`); skipped when DATABASE_URL is unreachable.
"""

from collections.abc import Iterator
from uuid import uuid4

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url

from greenink.core.settings import get_settings
from greenink.db.models import Base
from tests.conftest import REPO_ROOT

pytestmark = pytest.mark.db


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


def test_migrations_match_models_and_round_trip(scratch_database_url: str) -> None:
    config = Config(str(REPO_ROOT / "packages" / "greenink" / "db" / "alembic.ini"))
    engine = create_engine(scratch_database_url)
    try:
        with engine.begin() as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, "head")
            diff = compare_metadata(MigrationContext.configure(connection), Base.metadata)
            assert diff == []
            tables = set(inspect(connection).get_table_names())
            assert tables - {"alembic_version"} == set(Base.metadata.tables)
            command.downgrade(config, "base")
            assert set(inspect(connection).get_table_names()) == {"alembic_version"}
    finally:
        engine.dispose()
