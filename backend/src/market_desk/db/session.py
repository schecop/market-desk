"""Database sessions: one unit of work per request."""

from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy.orm import Session, sessionmaker

from market_desk.db.engine import get_engine


@lru_cache
def get_sessionmaker() -> sessionmaker[Session]:
    """Session factory bound to the app's engine (created once)."""
    return sessionmaker(bind=get_engine(), expire_on_commit=False)


def get_session() -> Iterator[Session]:
    """FastAPI dependency: open a session for the request, always close it after.

    Usage in a route: `session: Annotated[Session, Depends(get_session)]`.
    Routes call `session.commit()` themselves when they write.
    """
    with get_sessionmaker()() as session:
        yield session
