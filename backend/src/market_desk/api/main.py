"""FastAPI application entry point.

Run locally with: uv run uvicorn market_desk.api.main:app --reload
"""

from fastapi import FastAPI

app = FastAPI(title="Market Desk", version="0.1.0")


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness check: the process is up and serving requests.

    Sprint 0 task 2 extends this to also check the database connection.
    """
    return {"status": "ok"}
