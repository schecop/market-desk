from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine

from market_desk.api.main import app
from market_desk.db.engine import get_engine

pytestmark = pytest.mark.usefixtures("migrated_database")  # the test database exists


@pytest.fixture
def client() -> Iterator[TestClient]:
    yield TestClient(app)
    app.dependency_overrides.clear()  # never leak an override into the next test


def test_health_ok_when_database_is_up(client: TestClient) -> None:
    """Needs Postgres running (docker compose up -d locally, a service container in CI)."""
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}


def test_health_503_when_database_is_down(client: TestClient) -> None:
    # Port 1 has nothing listening, so the connection is refused immediately
    unreachable = create_engine(
        "postgresql+psycopg://nobody:nothing@127.0.0.1:1/none",
        connect_args={"connect_timeout": 1},
    )
    app.dependency_overrides[get_engine] = lambda: unreachable

    response = client.get("/health")

    assert response.status_code == 503
    assert response.json() == {"status": "degraded", "database": "unreachable"}
