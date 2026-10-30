"""Fakes shared by the tests: a fake SEC, a fake n8n and a fake Claude.

Apple's submissions fixture has three 10-Ks: NEWEST and the two OLDER ones.
"""

import base64
import json
from pathlib import Path
from typing import Any

import httpx2
from aiolimiter import AsyncLimiter
from anthropic import AsyncAnthropic

from market_desk.clients.edgar import EdgarClient
from market_desk.webhooks.outbound import WebhookDispatcher

FIXTURES = Path(__file__).parent / "fixtures" / "edgar"
SEC_ROUTES = {
    "https://www.sec.gov/files/company_tickers.json": "company_tickers.json",
    "https://data.sec.gov/submissions/CIK0000320193.json": "submissions_CIK0000320193.json",
}
SECRET = "whsec_" + base64.b64encode(b"0" * 32).decode()
N8N_URL = "https://n8n.test/webhook/market-desk"

APPLE_CIK = 320193
NEWEST = "0000320193-25-000079"  # filed 2025-10-31
OLDER = ["0000320193-24-000123", "0000320193-23-000106"]


async def no_sleep(seconds: float) -> None:
    pass


def fake_sec(request: httpx2.Request) -> httpx2.Response:
    """Known URLs answer with their fixture; anything else is a 404, like the SEC."""
    name = SEC_ROUTES.get(str(request.url))
    if name is None:
        return httpx2.Response(404)
    return httpx2.Response(200, content=(FIXTURES / name).read_bytes())


def make_edgar() -> EdgarClient:
    """An EDGAR client on the fake SEC: no network, no waiting, no rate limit."""
    return EdgarClient(
        "Market Desk tests@example.com",
        timeout=5,
        transport=httpx2.MockTransport(fake_sec),
        sleep=no_sleep,
        limiter=AsyncLimiter(10_000, 1),
    )


class FakeN8n:
    """Records every event it receives and answers with `status` (202 unless a test changes it)."""

    def __init__(self) -> None:
        self.status = 202
        self.events: list[dict[str, Any]] = []

    def handler(self, request: httpx2.Request) -> httpx2.Response:
        self.events.append(json.loads(request.content))
        return httpx2.Response(self.status)

    def dispatcher(self) -> WebhookDispatcher:
        return WebhookDispatcher(
            N8N_URL, SECRET, transport=httpx2.MockTransport(self.handler), sleep=no_sleep
        )


class FakeClaude:
    """The Messages API, scripted: answers each request with the next reply in `replies`.

    Records every request body in `requests`, so a test can check what the loop sent.
    A reply can also be an int: that HTTP status, with an error body (Claude failing).
    """

    def __init__(self, replies: list[dict[str, Any] | int]) -> None:
        self.replies = list(replies)
        self.requests: list[dict[str, Any]] = []

    def handler(self, request: httpx2.Request) -> httpx2.Response:
        self.requests.append(json.loads(request.content))
        reply = self.replies.pop(0)
        if isinstance(reply, int):
            error = {"type": "error", "error": {"type": "api_error", "message": "Fake failure"}}
            return httpx2.Response(reply, json=error)
        return httpx2.Response(200, json=reply)

    def client(self) -> AsyncAnthropic:
        # max_retries=0: a scripted failure fails at once instead of being retried
        transport = httpx2.MockTransport(self.handler)
        return AsyncAnthropic(
            api_key="test", max_retries=0, http_client=httpx2.AsyncClient(transport=transport)
        )


def claude_reply(content: list[dict[str, Any]], stop_reason: str) -> dict[str, Any]:
    """A Messages API response body with the given content blocks."""
    return {
        "id": "msg_test",
        "type": "message",
        "role": "assistant",
        "model": "claude-sonnet-5-5",
        "content": content,
        "stop_reason": stop_reason,
        "stop_sequence": None,
        "usage": {"input_tokens": 1000, "output_tokens": 200},
    }


def tool_call(name: str, arguments: dict[str, Any], tool_use_id: str = "toolu_1") -> dict[str, Any]:
    """A reply in which Claude asks for one tool."""
    block = {"type": "tool_use", "id": tool_use_id, "name": name, "input": arguments}
    return claude_reply([block], "tool_use")


def answer(text: str) -> dict[str, Any]:
    """A reply in which Claude answers and stops."""
    return claude_reply([{"type": "text", "text": text}], "end_turn")
