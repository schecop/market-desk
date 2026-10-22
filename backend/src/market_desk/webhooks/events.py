"""The events we send and receive. One envelope for every event type; `data` holds the details."""

from datetime import UTC, datetime
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field

# Every event type the system knows. A Literal makes an unknown type a validation error.
EventType = Literal[
    "test.ping",  # a no-op event to check that a receiver is wired up
    "filing.created",  # a watchlist company filed something new on EDGAR (task 7)
]


def new_event_id() -> str:
    """A unique id per event. It stays the same across delivery retries (the idempotency key)."""
    return f"msg_{uuid4().hex}"


class WebhookEvent(BaseModel):
    id: str = Field(default_factory=new_event_id)
    type: EventType
    # Timezone-aware UTC on purpose: Standard Webhooks signs Unix timestamps
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    data: dict[str, Any] = Field(default_factory=dict)
