"""The initial migration creates exactly the tables in greenink.db.models.

Needs Postgres (`docker compose up postgres`); skipped when DATABASE_URL is unreachable.
"""

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import Enum as SAEnum
from sqlalchemy import create_engine, inspect, text

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


def test_every_enum_value_passes_its_check_constraint(scratch_database_url: str) -> None:
    """Enum columns are VARCHAR + CHECK and autogenerate does not compare CHECKs, so adding an
    enum value without a migration would only fail at insert time. Catch it here."""
    config = Config(str(REPO_ROOT / "packages" / "greenink" / "db" / "alembic.ini"))
    engine = create_engine(scratch_database_url)
    try:
        with engine.begin() as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, "head")
        for table in Base.metadata.sorted_tables:
            for column in table.columns:
                if not isinstance(column.type, SAEnum) or column.type.enum_class is None:
                    continue
                enum = column.type.enum_class
                with engine.connect() as connection:
                    definition = connection.execute(
                        text(
                            "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
                            "WHERE conrelid = CAST(:table AS regclass) AND conname = :name"
                        ),
                        {"table": table.name, "name": f"ck_{table.name}_{column.type.name}"},
                    ).scalar_one()
                missing = [m.value for m in enum if f"'{m.value}'" not in definition]
                assert not missing, f"{table.name}.{column.name} CHECK lacks {missing}: add a migration"
    finally:
        engine.dispose()
