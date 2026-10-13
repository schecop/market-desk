"""Alembic environment: how migrations connect to the database.

Run from backend/: `uv run alembic upgrade head`, `uv run alembic revision -m "..."`.
"""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

from market_desk.config import get_settings
from market_desk.db.base import Base

config = context.config

# Logging setup from alembic.ini
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Autogenerate compares the database with this metadata.
# Model modules must be imported before this line once they exist (Sprint 1+).
target_metadata = Base.metadata

# Same source of truth as the app: DATABASE_URL env var / .env / default
DATABASE_URL = get_settings().database_url


def run_migrations_offline() -> None:
    """Emit SQL to stdout instead of running it (`alembic upgrade head --sql`)."""
    context.configure(
        url=DATABASE_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Connect to the database and apply migrations in a transaction."""
    # NullPool: a one-off command doesn't need a connection pool.
    # connect_timeout: fail in seconds instead of hanging when the DB is unreachable.
    connectable = create_engine(
        DATABASE_URL, poolclass=pool.NullPool, connect_args={"connect_timeout": 3}
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
