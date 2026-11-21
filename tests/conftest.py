"""Shared pytest fixtures.

The suite runs against a real PostgreSQL 16 database because this delivery
depends on native ``UUID``, ``UUID[]``, ``JSONB``, ``gen_random_uuid()`` and
``CHECK`` constraints.  ``TEST_DATABASE_URL`` is mandatory and the database
name must contain "test": the session fixture drops and recreates the ``public``
schema, so it must never point at a shared database.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from app import models  # noqa: F401,E402  (register metadata)
from app.db import Base  # noqa: F401,E402

DELIVERY_TABLES = ("opportunity_stage_log", "opportunity_meeting", "opportunity")


@pytest.fixture(scope="session")
def database_url() -> str:
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.exit(
            "TEST_DATABASE_URL is required, e.g. "
            "postgresql+psycopg://USER:PASSWORD@127.0.0.1:5432/DB_NAME_WITH_TEST",
            returncode=2,
        )

    parsed = make_url(url)
    if "test" not in (parsed.database or "").lower():
        pytest.exit(
            f"Refusing to run destructive fixtures against non-test database {parsed.database!r}",
            returncode=2,
        )
    return url


@pytest.fixture(scope="session")
def roundtrip_database_url(database_url: str):
    """A throwaway database so upgrade/downgrade round-trips never touch the suite DB."""

    import uuid as uuid_module

    parsed = make_url(database_url)
    admin_engine = create_engine(
        parsed.set(database="postgres"), isolation_level="AUTOCOMMIT", poolclass=NullPool
    )
    temp_name = f"clawhunt_2056_roundtrip_{uuid_module.uuid4().hex[:8]}"
    with admin_engine.connect() as connection:
        connection.execute(text(f'CREATE DATABASE "{temp_name}"'))

    url = parsed.set(database=temp_name).render_as_string(hide_password=False)
    try:
        yield url
    finally:
        with admin_engine.connect() as connection:
            connection.execute(text(f'DROP DATABASE IF EXISTS "{temp_name}" WITH (FORCE)'))
        admin_engine.dispose()


@pytest.fixture(scope="session")
def alembic_config(database_url: str) -> Config:
    os.environ["DATABASE_URL"] = database_url
    config = Config(str(BASE_DIR / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    return config


@pytest.fixture(scope="session")
def engine(database_url: str, alembic_config: Config):
    """Reset the public schema once, then apply the delivered migration."""

    eng = create_engine(database_url, poolclass=NullPool, future=True)
    with eng.connect() as connection:
        connection.execute(text("DROP SCHEMA public CASCADE"))
        connection.execute(text("CREATE SCHEMA public"))
        connection.commit()

    command.upgrade(alembic_config, "head")

    yield eng
    eng.dispose()


@pytest.fixture(autouse=True)
def clean_tables(engine):
    """Every test starts and ends with the three delivery tables empty."""

    statement = text(f"TRUNCATE {', '.join(DELIVERY_TABLES)} RESTART IDENTITY CASCADE")
    with engine.begin() as connection:
        connection.execute(statement)
    yield
    with engine.begin() as connection:
        connection.execute(statement)


@pytest.fixture()
def session(engine):
    factory = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    db = factory()
    try:
        yield db
    finally:
        db.rollback()
        db.close()
