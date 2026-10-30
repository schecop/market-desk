"""POST /chat end to end: a fake Claude, the real loop, tools and the test database.

Each test scripts Claude's replies (fakes.FakeClaude), sends a request, reads the SSE stream
and checks what was saved. Nothing calls a live API.
"""

import json
from collections.abc import Iterator
from typing import Any, cast

import pytest
from fakes import FakeClaude, answer, make_edgar, tool_call
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from market_desk.agent.services import AgentServices
from market_desk.api.chat import get_agent_services
from market_desk.api.main import app
from market_desk.db.models import Conversation, Message, ToolCall
from market_desk.db.session import get_sessionmaker

HEADERS = {"X-Client": "test"}  # the client_id fixture's slug


@pytest.fixture
def client(db_session: Session) -> Iterator[TestClient]:
    """The app on the test database. Each test sets `app.state.claude` replies via `use`."""
    # The route opens "a session" through this factory: hand it the test's session instead
    app.dependency_overrides[get_sessionmaker] = lambda: lambda: db_session
    yield TestClient(app)
    app.dependency_overrides.clear()


def use(claude: FakeClaude) -> None:
    """Run the agent on this fake Claude and the fake SEC. Cala isn't needed by these tests."""
    services = AgentServices(anthropic=claude.client(), cala=cast(Any, None), edgar=make_edgar())
    app.dependency_overrides[get_agent_services] = lambda: services


def events(body: str) -> list[tuple[str, dict[str, Any]]]:
    """Parse an SSE body into (event name, data) pairs."""
    parsed = []
    for message in body.strip().split("\n\n"):
        name_line, data_line = message.split("\n")
        parsed.append(
            (name_line.removeprefix("event: "), json.loads(data_line.removeprefix("data: ")))
        )
    return parsed


def names(body: str) -> list[str]:
    return [name for name, _ in events(body)]


def test_a_run_streams_its_events_and_saves_the_conversation(
    client: TestClient, db_session: Session, client_id: int
) -> None:
    use(FakeClaude([tool_call("list_watchlist", {}), answer("Your watchlist is empty.")]))

    response = client.post("/chat", json={"message": "What do I watch?"}, headers=HEADERS)

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert names(response.text) == ["conversation", "tool_use", "tool_result", "text", "done"]
    done = events(response.text)[-1][1]
    assert done["status"] == "done"
    assert done["answer"] == "Your watchlist is empty."
    assert done["steps"] == 2
    assert done["input_tokens"] == 2000

    # user question, tool_use, tool_result, answer: in order, tokens on the assistant ones
    rows = db_session.scalars(select(Message).order_by(Message.id)).all()
    assert [row.role for row in rows] == ["user", "assistant", "user", "assistant"]
    assert rows[0].content == [{"type": "text", "text": "What do I watch?"}]
    assert [row.input_tokens for row in rows] == [None, 1000, None, 1000]
    call = db_session.scalars(select(ToolCall)).one()
    assert call.status == "done"
    assert call.duration_ms is not None


def test_a_follow_up_sends_the_saved_history_to_claude(
    client: TestClient, db_session: Session, client_id: int
) -> None:
    claude = FakeClaude([answer("Hello."), answer("Still here.")])
    use(claude)
    first = client.post("/chat", json={"message": "Hi"}, headers=HEADERS)
    conversation_id = events(first.text)[0][1]["conversation_id"]

    client.post(
        "/chat", json={"message": "Again", "conversation_id": conversation_id}, headers=HEADERS
    )

    # The second call carries the first exchange, reloaded from Postgres, plus the new question
    sent = claude.requests[1]["messages"]
    assert [m["role"] for m in sent] == ["user", "assistant", "user"]
    assert sent[1]["content"] == [{"type": "text", "text": "Hello."}]


def test_a_write_tool_waits_and_blocks_new_messages(
    client: TestClient, db_session: Session, client_id: int
) -> None:
    use(FakeClaude([tool_call("add_to_watchlist", {"ticker": "AAPL"})]))

    response = client.post("/chat", json={"message": "Watch Apple"}, headers=HEADERS)

    done = events(response.text)[-1][1]
    assert done["status"] == "awaiting_approval"
    assert done["pending"] == [
        {"id": "toolu_1", "name": "add_to_watchlist", "input": {"ticker": "AAPL"}}
    ]
    assert db_session.scalars(select(ToolCall.status)).one() == "pending_approval"

    # A new message now would leave the tool_use without a tool_result: refused before streaming
    conversation_id = events(response.text)[0][1]["conversation_id"]
    again = client.post(
        "/chat", json={"message": "Hello?", "conversation_id": conversation_id}, headers=HEADERS
    )
    assert again.status_code == 409


def test_an_approval_runs_the_call_and_finishes_the_run(
    client: TestClient, db_session: Session, client_id: int
) -> None:
    use(FakeClaude([tool_call("add_to_watchlist", {"ticker": "AAPL"}), answer("Added Apple.")]))
    first = client.post("/chat", json={"message": "Watch Apple"}, headers=HEADERS)
    conversation_id = events(first.text)[0][1]["conversation_id"]

    response = client.post(
        f"/chat/{conversation_id}/approvals",
        json={"decisions": {"toolu_1": True}},
        headers=HEADERS,
    )

    assert names(response.text) == ["conversation", "tool_result", "text", "done"]
    assert events(response.text)[-1][1]["status"] == "done"
    assert db_session.scalars(select(ToolCall.status)).one() == "done"


def test_a_failure_mid_run_rolls_everything_back(
    client: TestClient, db_session: Session, client_id: int
) -> None:
    use(FakeClaude([500]))  # Claude fails on the first call

    response = client.post("/chat", json={"message": "Hi"}, headers=HEADERS)

    # Already streaming when it failed: still a 200, with the failure as the last event
    assert response.status_code == 200
    assert names(response.text) == ["conversation", "error"]
    # The conversation and the question were rolled back with the rest
    assert db_session.scalar(select(func.count()).select_from(Conversation)) == 0


def test_unknown_client_or_conversation_is_a_404(client: TestClient, client_id: int) -> None:
    use(FakeClaude([]))

    unknown_client = client.post("/chat", json={"message": "Hi"}, headers={"X-Client": "nobody"})
    unknown_conversation = client.post(
        "/chat",
        json={"message": "Hi", "conversation_id": "00000000-0000-4000-8000-000000000000"},
        headers=HEADERS,
    )

    assert unknown_client.status_code == 404
    assert unknown_conversation.status_code == 404


def test_without_api_keys_chat_is_a_503(client: TestClient) -> None:
    # No override and no lifespan run: app.state has no agent services
    response = client.post("/chat", json={"message": "Hi"})

    assert response.status_code == 503
