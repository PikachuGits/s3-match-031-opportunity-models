"""AC-1: the delivered migration upgrades and downgrades cleanly."""

from __future__ import annotations

from sqlalchemy import create_engine, inspect
from sqlalchemy.pool import NullPool

from tests import alembic_utils

TABLES = {"opportunity", "opportunity_meeting", "opportunity_stage_log"}


def _table_names(url: str) -> set[str]:
    engine = create_engine(url, poolclass=NullPool)
    try:
        return set(inspect(engine).get_table_names())
    finally:
        engine.dispose()


def test_upgrade_downgrade_upgrade_roundtrip(roundtrip_database_url):
    url = roundtrip_database_url

    alembic_utils.upgrade(url)
    assert alembic_utils.current_revision(url) == "0001_opportunity"
    assert TABLES <= _table_names(url)

    alembic_utils.downgrade(url)
    assert alembic_utils.current_revision(url) is None
    assert TABLES - _table_names(url) == TABLES

    alembic_utils.upgrade(url)
    assert TABLES <= _table_names(url)

    # Models and DDL agree: no pending autogenerate diff after a round trip.
    alembic_utils.check(url)
