# ADR-0008: Stream chat runs as Server-Sent Events from an event-yielding loop

- **Date:** 2026-10-30
- **Status:** accepted
- **Sprint:** 2

## Context
`POST /chat` runs the agent loop, which can take several model calls and tool calls. Waiting for the whole run before answering leaves the user staring at nothing for many seconds; the plan asks for a streaming response. Two questions: which protocol carries the stream to the browser, and how the loop hands over progress while it runs. The loop (`agent/loop.py`) must stay usable without HTTP: by tests, by the LangGraph comparison (task 7) and by a CLI.

## Options considered
1. **Server-Sent Events (`text/event-stream`)**: one-way server → client over plain HTTP; named events; trivial to test (read the body) and to proxy. One-way only, which chat doesn't need beyond the request itself.
2. **WebSockets**: two-way, lower overhead per message. Harder to proxy, authenticate and test; needed for voice in Sprint 5, where audio flows both ways, but more than chat needs.
3. **NDJSON over a chunked response**: simplest framing (one JSON object per line). No event names and no standard browser client.

For the loop's side:

1. **An async generator yielding events** (`stream_agent`): the caller iterates; each step is handed over as it happens; back-pressure for free (the loop only runs as fast as the client reads). The non-streaming `run_agent` drains it.
2. **An `on_event` callback**: fewer changes to the loop, but no back-pressure, and the HTTP response can't easily be driven from a callback.

## Decision
SSE with named events (`conversation`, `text`, `tool_use`, `tool_result`, `done`, `error`), produced by the route from domain events (`AssistantTurn`, `ToolResult`, `Done`) that the loop yields as an async generator. Answer text first streams per model turn (5a), then per token with `messages.stream()` (5b).

## Consequences
- Easier: one loop for streaming and non-streaming callers; tests read the stream as text; the frontend (Sprint 4) can use `fetch` with a stream reader.
- Harder: after the first byte the HTTP status is fixed at 200, so every failure past the up-front checks must be an `error` event, and clients must treat a stream that ends without `done` as failed. `EventSource` only does GET, so the browser needs `fetch` for these POSTs.
- Revisit: voice (Sprint 5) uses WebSockets; if chat ever needs to send while receiving (cancel a run mid-way), consider moving it there too.
