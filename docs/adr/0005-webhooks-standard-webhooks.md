# ADR-0005: Webhooks signed with the Standard Webhooks spec

- **Date:** 2026-10-21
- **Status:** accepted
- **Sprint:** 1

## Context
Market Desk receives events (inbound webhooks) and sends them, for example "a watchlist company filed a new 10-K" to n8n, which posts it to Slack. Anyone can POST to a public URL, so both directions need a way to prove who sent a request and that it wasn't altered or replayed. Senders also need to know when a delivery failed and what to retry.

## Options considered
**Signature format**
1. **Our own scheme** (e.g. an HMAC of the body in a custom header): simple. Cons: every detail is ours to get right (what is signed, timestamps, encoding, secret rotation), and no other tool speaks it.
2. **Copy one provider's format** (e.g. Stripe's `t=...,v1=...`): proven. Cons: tied to one vendor's conventions.
3. **Standard Webhooks** ([spec](https://www.standardwebhooks.com)), an open specification: headers `webhook-id`, `webhook-timestamp`, `webhook-signature`; signs `id.timestamp.body` with HMAC-SHA256; signature `v1,<base64>`, several space-separated for zero-downtime secret rotation; secrets prefixed `whsec_`.

**Implementation**
1. **The `standardwebhooks` library** (the spec's reference implementation; MIT; no dependencies; ~80 lines): `Webhook(secret).sign(...)` and `.verify(body, headers)`, with a constant-time comparison and a 5-minute timestamp tolerance.
2. **Hand-written** with `hmac` and `base64` (~30 lines): more learning. Cons: security code is where a subtle mistake costs the most.

## Decision
Standard Webhooks for both directions, through the `standardwebhooks` library. Inbound: `POST /webhooks/inbound`, verified in a FastAPI dependency (no secret configured → 503; bad signature, stale timestamp or missing headers → 401; valid signature but invalid event → 422), answered with `202` at once and processed with `BackgroundTasks`, deduplicated by `webhook-id`. Outbound: a `WebhookDispatcher` that signs `event.model_dump_json()` and POSTs it, with tenacity retries (3 attempts) for 5xx, 429 and network errors, the same `webhook-id` on every attempt, no retry on other 4xx, and `410 Gone` as a distinct error.

Two details found by reading the library's code:
- It verifies the exact bytes it's given, so the endpoint must pass the **raw** body, never re-serialized JSON.
- A `webhook-signature` header without a comma makes it raise `ValueError`, not `WebhookVerificationError`. The verification catches both, so a malformed header is a 401, not a 500. `sign()` also treats a naive `datetime` as UTC, so senders pass `datetime.now(UTC)`.

## Consequences
- Easier: any tool that implements Standard Webhooks can talk to us; secret rotation is built into the format; the security-sensitive parts are a reviewed library, not our code.
- Harder: the idempotency store is in memory (lost on restart, not shared between processes) until there is a database table for it (task 7).
- Revisit: the spec recommends retrying for **days** with growing gaps. A request-scoped dispatcher can only retry for seconds; durable delivery needs a persistent queue (an outbox table and a worker), a later sprint.
