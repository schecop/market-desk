"""FastAPI application entry point.

Run locally with: uv run uvicorn market_desk.api.main:app --reload
"""

from typing import Annotated

from fastapi import Depends, FastAPI, Response, status
from sqlalchemy import Engine

from market_desk.db.engine import database_is_reachable, get_engine
from market_desk.webhooks.inbound import router as webhooks_router

app = FastAPI(title="Market Desk", version="0.1.0")
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
