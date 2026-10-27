"""The initial migration creates exactly the tables in greenink.db.models.

Needs Postgres (`docker compose up postgres`); skipped when DATABASE_URL is unreachable.
"""

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, inspect

from greenink.db.models import Base
from tests.conftest import REPO_ROOT

pytestmark = pytest.mark.db


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
