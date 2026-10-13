"""SQLAlchemy engine: one connection pool shared by the whole app."""

from functools import lru_cache

from sqlalchemy import Engine, create_engine, text

from market_desk.config import get_settings


@lru_cache
def get_engine() -> Engine:
    """Create the engine once; it manages a pool of connections."""
    return create_engine(
        get_settings().database_url,
        # Test pooled connections before use; drops dead ones after a DB restart
        pool_pre_ping=True,
        connect_args={"connect_timeout": 3},  # fail fast instead of hanging when the DB is down
    )


def database_is_reachable(engine: Engine) -> bool:
    """Run a trivial query; True if Postgres answered."""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
