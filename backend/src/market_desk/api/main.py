"""FastAPI application entry point.

Run locally with: uv run uvicorn market_desk.api.main:app --reload
"""

import asyncio
import contextlib
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, FastAPI, Response, status
from sqlalchemy import Engine

from market_desk.config import get_settings
from market_desk.db.engine import database_is_reachable, get_engine
from market_desk.jobs.check_filings import filing_check_loop
from market_desk.webhooks.inbound import router as webhooks_router


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Code before `yield` runs at startup, after it at shutdown."""
    minutes = get_settings().filing_check_interval_minutes
    task = asyncio.create_task(filing_check_loop(minutes)) if minutes > 0 else None
    yield
    if task is not None:
        task.cancel()  # stop the timer cleanly instead of killing it mid-request
        with contextlib.suppress(asyncio.CancelledError):
            await task


app = FastAPI(title="Market Desk", version="0.1.0", lifespan=lifespan)
app.include_router(webhooks_router)


@app.get("/health")
def health(
    response: Response,
    engine: Annotated[Engine, Depends(get_engine)],
) -> dict[str, str]:
    """Readiness check: the process is up and Postgres answers queries.

    Returns 503 when the database is unreachable, so a load balancer
    (Sprint 7) stops sending traffic to this instance.
    """
    if database_is_reachable(engine):
        return {"status": "ok", "database": "ok"}
    response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {"status": "degraded", "database": "unreachable"}
