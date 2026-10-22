"""Inbound webhooks: POST /webhooks/inbound, verified before the endpoint runs (ADR-0005)."""

import logging
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from pydantic import ValidationError
from standardwebhooks import Webhook, WebhookVerificationError

from market_desk.config import Settings, get_settings
from market_desk.webhooks.events import WebhookEvent

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks", tags=["webhooks"])

# Event ids already accepted, for idempotency: a sender retries with the same webhook-id.
# In memory, so it's lost on restart and not shared between processes; a database table
# replaces it once there is one (task 7).
_seen_ids: set[str] = set()


async def verified_event(
    request: Request, settings: Annotated[Settings, Depends(get_settings)]
) -> WebhookEvent:
    """FastAPI dependency: the request's event, only if its Standard Webhooks signature is valid."""

    if settings.webhook_signing_secret is None:
        raise HTTPException(status_code=503, detail="No webhook signing secret configured")

    body = await request.body()
    headers = dict(request.headers)
    try:
        Webhook(settings.webhook_signing_secret.get_secret_value()).verify(
            body, headers, json_parse=False
        )
    except (ValueError, WebhookVerificationError) as err:
        raise HTTPException(status_code=401, detail="Request cannot be verified") from err

    try:
        return WebhookEvent.model_validate_json(body)
    except ValidationError as err:
        raise HTTPException(
            status_code=422, detail="Cannot parse the request to a WebhookEvent"
        ) from err


def handle_event(event: WebhookEvent) -> None:
    """The actual work, after the response was sent. For now it only logs the event."""
    logger.info("Webhook event %s (%s) received: %s", event.id, event.type, event.data)


@router.post("/inbound", status_code=status.HTTP_202_ACCEPTED)
def receive_webhook(
    event: Annotated[WebhookEvent, Depends(verified_event)],
    background: BackgroundTasks,
) -> dict[str, str]:
    """Answer fast (202) and do the work in the background: the sender has a timeout and retries."""
    if event.id in _seen_ids:
        # Already accepted: acknowledge again so the sender stops retrying, but don't redo the work
        return {"status": "duplicate", "id": event.id}
    _seen_ids.add(event.id)
    background.add_task(handle_event, event)
    return {"status": "accepted", "id": event.id}
