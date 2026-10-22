"""Inbound webhooks: only correctly signed, fresh, well-formed events get through (ADR-0005).

Each test signs like a correct sender (signed_headers), then breaks one thing on purpose.
"""

import base64
import hashlib
import hmac
import logging
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from standardwebhooks import Webhook

from market_desk.api.main import app
from market_desk.config import Settings, get_settings
from market_desk.webhooks import inbound

# A fixed, test-only secret: "whsec_" + base64 of 32 known bytes
SECRET_BYTES = bytes(range(32))
SECRET = "whsec_" + base64.b64encode(SECRET_BYTES).decode()
OTHER_SECRET = "whsec_" + base64.b64encode(bytes(range(32, 64))).decode()

BODY = b'{"id":"msg_1","type":"test.ping","created_at":"2026-10-21T10:00:00Z","data":{}}'


def signed_headers(
    body: bytes,
    *,
    msg_id: str = "msg_1",
    secret: str = SECRET,
    timestamp: datetime | None = None,
) -> dict[str, str]:
    """The three Standard Webhooks headers a correct sender would attach to `body`."""
    timestamp = timestamp or datetime.now(UTC)
    signature = Webhook(secret).sign(msg_id=msg_id, timestamp=timestamp, data=body.decode())
    return {
        "webhook-id": msg_id,
        "webhook-timestamp": str(int(timestamp.timestamp())),
        "webhook-signature": signature,
        "Content-Type": "application/json",
    }


@pytest.fixture
def client() -> Iterator[TestClient]:
    """The app with the test secret configured, and a clean idempotency store."""
    app.dependency_overrides[get_settings] = lambda: Settings(
        webhook_signing_secret=SecretStr(SECRET)
    )
    inbound._seen_ids.clear()
    yield TestClient(app)
    app.dependency_overrides.clear()
    inbound._seen_ids.clear()


# --- accepted ---


def test_valid_event_is_accepted(client: TestClient) -> None:
    response = client.post("/webhooks/inbound", content=BODY, headers=signed_headers(BODY))

    assert response.status_code == 202
    assert response.json()["status"] == "accepted"
    assert response.json()["id"] == "msg_1"


def test_accepted_event_is_handled_in_the_background(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.INFO, logger="market_desk.webhooks.inbound"):
        client.post("/webhooks/inbound", content=BODY, headers=signed_headers(BODY))

    # TestClient runs background tasks before returning, so the work has happened by now
    assert len(caplog.records) == 1
    assert "msg_1" in caplog.records[0].getMessage()


def test_duplicate_event_is_acknowledged_but_not_handled_twice(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.INFO, logger="market_desk.webhooks.inbound"):
        first = client.post("/webhooks/inbound", content=BODY, headers=signed_headers(BODY))
        second = client.post("/webhooks/inbound", content=BODY, headers=signed_headers(BODY))

    # Both acknowledged (so the sender stops retrying), but the work ran only once
    assert first.status_code == second.status_code == 202
    assert first.json()["status"] == "accepted"
    assert second.json() == {"status": "duplicate", "id": "msg_1"}
    assert len(caplog.records) == 1


# --- rejected: 401 ---


def test_wrong_secret_is_rejected(client: TestClient) -> None:
    headers = signed_headers(BODY, secret=OTHER_SECRET)
    response = client.post("/webhooks/inbound", content=BODY, headers=headers)

    assert response.status_code == 401


def test_tampered_body_is_rejected(client: TestClient) -> None:
    # Signed for BODY, but one byte of the sent body was changed on the way
    tampered = BODY.replace(b"test.ping", b"test.pong")
    response = client.post("/webhooks/inbound", content=tampered, headers=signed_headers(BODY))

    assert response.status_code == 401


def test_old_timestamp_is_rejected(client: TestClient) -> None:
    # A captured request replayed 10 minutes later: the signature is valid, the time isn't
    old = datetime.now(UTC) - timedelta(minutes=10)
    response = client.post(
        "/webhooks/inbound", content=BODY, headers=signed_headers(BODY, timestamp=old)
    )

    assert response.status_code == 401


def test_missing_headers_are_rejected(client: TestClient) -> None:
    response = client.post(
        "/webhooks/inbound", content=BODY, headers={"Content-Type": "application/json"}
    )

    assert response.status_code == 401


def test_malformed_signature_header_is_401_not_500(client: TestClient) -> None:
    # The library raises ValueError (not its own error) for a signature without a comma
    headers = {**signed_headers(BODY), "webhook-signature": "garbage"}
    response = client.post("/webhooks/inbound", content=BODY, headers=headers)

    # A 500 here would mean the library's ValueError escaped the dependency
    assert response.status_code == 401


# --- rejected: other statuses ---


def test_validly_signed_but_unknown_event_type_is_422(client: TestClient) -> None:
    body = BODY.replace(b"test.ping", b"nonsense.type")
    response = client.post("/webhooks/inbound", content=body, headers=signed_headers(body))

    # The signature is fine (who sent it); the content isn't a valid event (what it says)
    assert response.status_code == 422


def test_no_secret_configured_is_503(client: TestClient) -> None:
    app.dependency_overrides[get_settings] = lambda: Settings(webhook_signing_secret=None)
    response = client.post("/webhooks/inbound", content=BODY, headers=signed_headers(BODY))

    # Without a secret nothing can be verified, so everything is refused, signed or not
    assert response.status_code == 503


# --- what the library does, by hand ---


def test_signature_is_hmac_sha256_of_id_timestamp_body() -> None:
    # Recompute a Standard Webhooks signature with nothing but hmac, hashlib and base64,
    # and check it matches what the library produced. Proves you know what's being signed.
    timestamp = datetime(2026, 10, 21, 10, 0, tzinfo=UTC)
    from_library = Webhook(SECRET).sign(msg_id="msg_1", timestamp=timestamp, data=BODY.decode())

    digest = hmac.new(
        SECRET_BYTES, f"msg_1.{int(timestamp.timestamp())}.{BODY.decode()}".encode(), hashlib.sha256
    ).digest()
    assert f"v1,{base64.b64encode(digest).decode()}" == from_library
