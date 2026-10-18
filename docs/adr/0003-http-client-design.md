# ADR-0003: HTTP client design (httpx2, async, tenacity, MockTransport)

- **Date:** 2026-10-16
- **Status:** accepted
- **Sprint:** 1

## Context
Sprint 1 builds typed clients for Cala and SEC EDGAR. They are the base for every tool the agent calls from Sprint 2 on. Four choices shape all of them: the HTTP library, sync or async, how retries are written, and how tests fake the network. Constraints: CI must never call live APIs, and Cala's free tier allows only 100 calls in total, so the test setup must make every failure mode reproducible offline.

## Options considered
**HTTP library**
1. **`httpx`**: the plan's original choice, widely documented. Cons: no release since 0.28.1 (December 2024). Starlette's TestClient has already moved away from it.
2. **`httpx2`**: the maintained successor (same author, maintained by Pydantic), same API, already a dependency for the TestClient. Cons: younger, fewer answers online under its new name.

**Sync or async**
1. **Sync `Client`**: simpler to write and test. Cons: blocks FastAPI's event loop, can't run tool calls in parallel, and the voice pipeline (Sprint 5) would force a rewrite.
2. **Async `AsyncClient`**: fits FastAPI, parallel tool calls (Cala and EDGAR at once), and streaming voice. Cons: `async`/`await` from the start, and async tests (`pytest.mark.anyio`).

**Retries**
1. **A hand-written loop**: full control over `Retry-After` and quota-vs-rate 429s. Cons: reinvents a solved problem; more code to maintain.
2. **tenacity**: the standard Python retry library; declarative (`stop=`, `wait=`, `retry=`), readable and tested. Cons: honouring `Retry-After` needs a custom `wait` callable.

**Test mocks**
1. **respx**: the plan's original choice. Cons: it patches `httpx` only (`requires httpx>=0.25`), so it doesn't see `httpx2` requests.
2. **`httpx2.MockTransport`**: built into the library. The client takes a transport in its constructor, and tests pass a function that returns any response (429, 500, malformed JSON, timeout).

## Decision
`httpx2.AsyncClient`, retries with **tenacity**, and tests through an injected **`httpx2.MockTransport`**. Each client owns auth, timeouts, retries (429, 5xx and network errors, never 4xx validation errors) and maps errors to its own exception hierarchy, returning Pydantic models.

## Consequences
- Easier: one testing pattern for every client (dependency injection, no global patching); parallel tool calls later.
- Harder: async everywhere it touches; the `Retry-After` wait is custom code on top of tenacity.
- Revisit: if `httpx2` stalls or respx adds support, re-evaluate. Cala's quota-exhausted `429` (if it differs from a rate-limit `429`) must not be retried.
- `docs/PLAN.md` (sections 5 and 8) and `CLAUDE.md` now say `httpx2` and `MockTransport` instead of `httpx` and respx.
