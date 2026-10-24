"""Shared test setup. Tests use their own database, so they never touch dev data.

pytest imports this file before any test module, so DATABASE_URL is switched before the app
reads its settings (`get_settings()` is cached on first call).
"""

import os
from collections.abc import Iterator

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, make_url, text
from sqlalchemy.engine import URL
from sqlalchemy.orm import Session

from market_desk.config import Settings
from market_desk.db.models import Client

TEST_DATABASE = "market_desk_test"

# Same server and credentials as the app's database, different database name
_app_url = make_url(Settings().database_url)
TEST_DATABASE_URL: URL = _app_url.set(database=TEST_DATABASE)
os.environ["DATABASE_URL"] = TEST_DATABASE_URL.render_as_string(hide_password=False)


def _create_test_database() -> None:
    """CREATE DATABASE if it's missing, from the server's `postgres` database."""
    admin = create_engine(
        _app_url.set(database="postgres"),
        isolation_level="AUTOCOMMIT",  # CREATE DATABASE can't run inside a transaction
        connect_args={"connect_timeout": 3},
    )
    with admin.connect() as conn:
        exists = conn.execute(
            text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": TEST_DATABASE}
        ).first()
        if not exists:
            conn.execute(text(f'CREATE DATABASE "{TEST_DATABASE}"'))
    admin.dispose()


def alembic_config() -> Config:
    config = Config("")
    config.set_main_option("script_location", "market_desk:db:migrations")
    return config


@pytest.fixture(scope="session")
def migrated_database() -> None:
    """The test database, created if needed and migrated to head. Once per test run."""
    _create_test_database()
    command.upgrade(alembic_config(), "head")


@pytest.fixture
def db_session(migrated_database: None) -> Iterator[Session]:
    """A session whose changes are all rolled back after the test, even ones it committed.

    The test runs inside an outer transaction; the session's own commits become savepoints
    inside it (join_transaction_mode), so the rollback at the end undoes everything.
    """
    engine = create_engine(TEST_DATABASE_URL)
    with engine.connect() as connection:
        outer = connection.begin()
        with Session(
            bind=connection, join_transaction_mode="create_savepoint", expire_on_commit=False
        ) as session:
            yield session
        outer.rollback()
    engine.dispose()


@pytest.fixture
def client_id(db_session: Session) -> int:
    """A client of its own for the test, so no test depends on the migration's default client."""
    client = Client(slug="test", name="Test client")
    db_session.add(client)
    db_session.commit()
    return client.id
