---
tags:
  - http
  - integrations
  - security
---

# 5. Webhooks

**Sprint 1** · **Date:** 2026-10-21 · **Plan item:** `webhooks/`: inbound endpoint verifying an HMAC signature; outbound dispatcher with signing and retries

## What and why
Webhooks in both directions. **Inbound:** `POST /webhooks/inbound` accepts an event only if it's signed with our shared secret, recent, and new (not a duplicate). **Outbound:** a dispatcher that signs our events and delivers them to a URL (n8n, in task 6), retrying on failure. Tasks 6 and 7 build on it: n8n posting to Slack, and the "new 10-K" check.

## Decisions
| Date | Decision | Why | Alternatives considered | ADR |
|---|---|---|---|---|
| 2026-10-21 | Sign with the open **Standard Webhooks** spec | Covers signature, timestamp, idempotency id and secret rotation; any tool implementing it can talk to us | Our own scheme; copying Stripe's format | [ADR-0005](../../adr/0005-webhooks-standard-webhooks.md) |
| 2026-10-21 | Use the `standardwebhooks` library | The spec's reference implementation, no dependencies; security code is the worst place for a hand-written mistake | Hand-written `hmac` + `base64` | [ADR-0005](../../adr/0005-webhooks-standard-webhooks.md) |
| 2026-10-21 | Verify in a FastAPI dependency; 503 / 401 / 422 / 202 | The endpoint only ever sees verified events; each failure has a distinct status | Verify inside the endpoint; middleware for all routes | |
| 2026-10-21 | Answer 202 and process with `BackgroundTasks`; dedupe by `webhook-id` (in memory for now) | Senders time out and retry; the same id must not be processed twice | Process before answering; dedupe in the database (no table yet) | |
| 2026-10-21 | One secret (`WEBHOOK_SIGNING_SECRET`) for both directions, for now | One shared counterpart (n8n) today | A secret per endpoint (needed once there are several receivers) | |

## Concepts
### Authentication vs authorization (401 vs 403)
**401** means *unauthenticated*: "I can't verify who you are", e.g. no valid signature. **403** means *unauthorized*: "I know who you are, and you may not do this". A bad webhook signature is a 401: there is no identity to authorize.

### Webhooks
An HTTP request that one system sends to another **when something happens**, instead of the other side polling ("anything new?") on a timer. The receiver exposes a URL; the sender POSTs an event to it.

### HMAC signatures
HMAC-SHA256 mixes a message with a secret key into a fixed-size fingerprint. Only someone who holds the key can produce the right fingerprint for a message, and changing a single byte of the message changes the fingerprint completely. Standard Webhooks signs `"<id>.<timestamp>.<body>"`, so the id and the time are protected too.

### Timing attacks and `hmac.compare_digest`
`a == b` stops at the first differing byte, so it returns slightly faster the earlier the mismatch is. Measured over many requests, that timing leaks how much of a guessed signature is right. `hmac.compare_digest` takes the same time whatever the inputs, so it leaks nothing. The library uses it.

### Replay attacks
A captured request with a valid signature stays valid forever, unless the signature covers a timestamp and the receiver rejects old ones. The library accepts a window of ±5 minutes.

## Code map
| File | What it does | Why it exists / why this way |
|---|---|---|
| `backend/src/market_desk/config.py` | `webhook_signing_secret` (`SecretStr`), `n8n_webhook_url` | Same optional-setting pattern as the clients |
| `.env.example` | `WEBHOOK_SIGNING_SECRET` with the command that generates one | `whsec_` + base64 of 32 random bytes |
| `backend/src/market_desk/webhooks/events.py` | `WebhookEvent` (id, type, created_at, data); `EventType` as a `Literal` | One envelope for every event; unknown types fail validation |
| `backend/src/market_desk/webhooks/inbound.py` | Router `POST /webhooks/inbound`, the `verified_event` dependency, `handle_event`, the in-memory idempotency store | Verification before the endpoint runs; fast 202 |
| `backend/src/market_desk/webhooks/outbound.py` | `WebhookDispatcher`, `WebhookDeliveryError`, `WebhookEndpointGoneError` | Signed delivery with retries |
| `backend/tests/test_webhooks_inbound.py` | 11 tests: accepted, handled in the background, duplicates, the 401s (wrong secret, tampered body, old timestamp, missing headers, malformed header), 422, 503, and a signature recomputed by hand with `hmac` | Each test signs like a correct sender, then breaks one thing |
| `backend/tests/test_webhooks_outbound.py` | 7 tests: POST to the URL, **a receiver can verify what was sent**, retries with the same id, retries exhausted, network errors, no retry on 400, 410 | Checks sending against receiving, not just that headers exist |
| `backend/src/market_desk/api/main.py` | `app.include_router(webhooks_router)` | Mounts the endpoint |

## Gotchas
!!! bug "Every valid event came back 422"
    **Symptom:** correctly signed events got `422 Cannot parse the request to a WebhookEvent`; every rejection test was right.
    **Cause:** `Webhook.verify()` parses the JSON by default and returns a **dict**; `WebhookEvent.model_validate_json(dict)` expects JSON *text* and raised `ValidationError` (`json_type`), which the `except ValidationError` turned into a plausible-looking 422.
    **Fix:** `verify(body, headers, json_parse=False)`, then `WebhookEvent.model_validate_json(body)`: one parse, by Pydantic.
    **Lesson:** a broad `except` can disguise your own bug as a legitimate error. Read what a library function returns, not just what it checks.

!!! bug "The dispatcher reported every successful delivery as a failure"
    **Symptom:** `WebhookDeliveryError` even when the receiver answered 200.
    **Cause:** four bugs: `base_url=url` plus `post("webhooks/inbound")` sent to the wrong URL; no `content=`, so the body was empty while the signature covered the JSON; a `raise WebhookDeliveryError()` after the `with attempt:` block ran on success; and 3xx counted as success.
    **Fix:** POST to the URL as given, sign and send one `body` string serialized once, `return` inside `with attempt:`, and treat anything that isn't 2xx as an error.
    **Lesson:** test sending *against* receiving: `test_receiver_can_verify_the_signature` would catch a body/signature mismatch that a header check misses.

!!! bug "A hand-computed signature didn't match the library's"
    **Symptom:** `v1,8032C0rg...` instead of `v1,bpffYFA/...`.
    **Cause:** `f"msg_1.{timestamp}..."` put the datetime's readable form (`2026-10-21 10:00:00+00:00`) in the signed content; the spec signs Unix seconds (`1792576800`).
    **Fix:** `int(timestamp.timestamp())`.
    **Lesson:** an HMAC changes completely on a one-character difference: that's the property that makes it a signature, and why both sides must build the exact same bytes.

!!! bug "The library raises `ValueError` for a malformed signature header"
    **Symptom:** (found reading its code, then confirmed) `webhook-signature: garbage` with a fresh timestamp raises `ValueError: not enough values to unpack`, not `WebhookVerificationError`.
    **Cause:** `version, signature = versioned_sig.split(",")` runs before any check on the header's shape.
    **Fix:** the verification catches both exceptions and answers 401; `test_malformed_signature_header_is_401_not_500` guards it.
    **Lesson:** read the code of a security library you depend on; "it raises X on failure" is a claim to check, not assume.

## Check questions
??? question "`send` makes a fresh timestamp and signature per attempt but keeps the `webhook-id`. What if the timestamp were made once, before the loop, and retries lasted 10 minutes?"
    The receiver accepts timestamps within ±5 minutes. A retry at minute 6 carries a 6-minute-old timestamp, so it's rejected as too old with a **401**; a 4xx isn't retried, so the dispatcher gives up and the event is **lost**, even though the receiver was back. Each attempt is a new delivery (fresh timestamp and signature); the id stays the same so the receiver can deduplicate.

??? question "Why does a bad signature get 401, not 403 or 400?"
    **401 Unauthorized** really means *unauthenticated*: "I can't verify who you are"; no valid signature, no identity. **403 Forbidden** is *authorization*: "I know who you are, and you may not do this". **400** says nothing about identity, so the sender wouldn't know to check the secret or the clock.


## Guided exercise
**Task (complete code left with a `TODO`):** recompute a Standard Webhooks signature by hand, with only `hmac`, `hashlib` and `base64`, and assert it equals the library's.

**Outcome:** done: `hmac.new(SECRET_BYTES, f"msg_1.{int(timestamp.timestamp())}.{body}".encode(), hashlib.sha256).digest()`, base64-encoded and prefixed with `v1,`, equals `Webhook(SECRET).sign(...)`.

**What I got wrong:** first the message id as the HMAC key and the body alone as the message; the HMAC object instead of `.digest()`; `b64encode` bytes inside an f-string (`b'...'`). Then the datetime's readable form instead of Unix seconds (see Gotchas). Also, earlier in the task: `model_validate_json` on the dict `verify()` returns, and four bugs in the dispatcher.

**Lesson:** the key is the secret's **raw bytes** (`SECRET_BYTES`); `whsec_...` is only its text format for storage, and the library strips the prefix and decodes the base64. The signed content is `id.timestamp.body`, so none of the three can be changed or replayed.

## Explain it in 2 minutes
Webhooks are HTTP calls a system makes when something happens. Anyone can POST to a public URL, so every webhook carries a signature: an HMAC-SHA256 of the event id, a Unix timestamp and the raw body, keyed with a secret both sides share. We use the open Standard Webhooks spec and its reference library rather than inventing a scheme. Inbound, a FastAPI dependency verifies before the endpoint runs: no secret configured is a 503, a wrong signature, tampered body, missing header or a timestamp older than five minutes is a 401, and a valid signature on an invalid event is a 422. The comparison is constant-time, so response timing leaks nothing, and the timestamp stops replays. An accepted event gets a 202 at once and is processed in the background, and its id makes processing idempotent: a retried delivery is acknowledged but not handled twice. Outbound, the dispatcher serializes the event once, signs exactly those bytes, and retries 5xx, 429 and network errors with the same id but a fresh timestamp; other 4xx aren't retried and a 410 means stop. The limit: retries last seconds, while the spec suggests days; durable delivery needs a persistent queue, which is a later sprint.
