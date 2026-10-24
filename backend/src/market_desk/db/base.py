"""Declarative base class that every table model inherits from."""

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

# Deterministic constraint names, so Alembic migrations can find and alter them later.
# Without this, Postgres invents names and autogenerate can't match them reliably.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    # column_0_N_name joins every column: (client_id, ticker) → uq_watchlists_client_id_ticker
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)
