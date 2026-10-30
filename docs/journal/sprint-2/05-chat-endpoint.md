---
tags:
  - agents
  - fastapi
  - streaming
  - postgres
---

# 5. `POST /chat`: the agent over HTTP, streamed

**Sprint 2** · **Date:** 2026-10-30 · **Plan item:** `POST /chat` endpoint (streaming response) using the loop

## What and why
The agent gets its first real caller. `POST /chat` takes a message, reloads the conversation from Postgres, runs the loop and streams what happens (tool calls, results, the answer) as Server-Sent Events. Then it saves the run and commits once. `POST /chat/{id}/approvals` resumes a run that's waiting for a human. The work comes in two steps: **5a** (this page so far) streams one event per loop step; **5b** streams the answer's text token by token with `messages.stream()`.

## Decisions
| Date | Decision | Why | Alternatives considered | ADR |
|---|---|---|---|---|
| 2026-10-30 | Stream with Server-Sent Events (`text/event-stream`), named events | One-way server → browser is all chat needs; plain HTTP, easy to proxy and test; named events tell the browser what each chunk is | WebSockets (two-way, harder to proxy and test; they come with voice in Sprint 5); NDJSON (no event names, no standard client) | [ADR-0008](../../adr/0008-chat-streaming-sse.md) |
| 2026-10-30 | The loop yields events (`stream_agent`, `stream_resume`); `run_agent` and `resume_agent` consume them | One loop for both callers; a generator is the shape `StreamingResponse` wants, and it only runs as fast as the client reads | An `on_event` callback (no back-pressure); two separate loops | [ADR-0008](../../adr/0008-chat-streaming-sse.md) |
| 2026-10-30 | Events describe the agent (`AssistantTurn`, `ToolResult`, `Done`); the route turns them into SSE | The loop knows nothing about HTTP; tests, LangGraph's comparison and a CLI can read the same events | Yield SSE strings from the loop | — |
| 2026-10-30 | Two steps: 5a event-level, 5b token-level | Each step teaches one thing; if both land together and something breaks, it's unclear which half did it | Token streaming at once | — |
| 2026-10-30 | Everything that can fail cleanly is checked before the stream starts (unknown client or conversation: 404; waiting for approval: 409; no API keys: 503) | After the first byte the status is 200 for good; only checks done before can return a real status code | Check inside the stream and send `error` events for everything | — |
| 2026-10-30 | One unit of work per request: save and commit when `Done` arrives, then send `done`; on any exception roll back everything and send `error` | The history never holds a `tool_use` without its `tool_result` (the API would reject it); a client that sees `done` knows the run is stored | Save error tool_results and keep the user's message (more code, a broken turn in the history) | — |
| 2026-10-30 | The route opens the session; the stream closes it in `finally`. `get_sessionmaker` is the dependency | Starlette runs the stream after the route function returns; a session from `Depends(get_session)` may already be closed by then | `Depends(get_session)` (lifetime depends on FastAPI's version) | — |
| 2026-10-30 | Anthropic, Cala and EDGAR clients built once in the lifespan (`agent/services.py`), `None` without keys (503) | One connection pool per service for the whole app; the app and CI start without keys | A client per request (a new TLS handshake each time) | — |
| 2026-10-30 | Which client is asking: an `X-Client` header, `default` if absent | A stand-in until per-client API keys in Sprint 4; keeps this task about streaming | Build API keys now (a table, hashing, rotation) | — |
| 2026-10-30 | History reloaded as dicts; `stream_resume` converts tool_use dicts with `ToolUseBlock.model_validate` (note 1 from task 4) | Convert at the boundary: one typed shape inside the loop | Make the whole loop accept dicts | — |
| 2026-10-30 | `resume_agent`'s step and token counts restart at zero (note 2 from task 4): accepted | Each run reports its own cost; per-message tokens in the DB give totals; a human sits between the two runs, so the step limit still bounds each part | Pass the earlier counts in | — |
| 2026-10-30 | `tool_calls` rows start `pending_approval`; results move them to `done`, `error` or `rejected`. In a waiting turn all calls wait, reads included | Matches the loop: none of that turn's calls has run yet | A separate "waiting" status for reads (the CHECK constraint doesn't have one) | — |

## Concepts

### Server-Sent Events (SSE)
A plain HTTP response that stays open and carries messages as they happen. Each message is an `event:` line, a `data:` line and a blank line:

```
event: tool_use
data: {"id": "toolu_1", "name": "list_watchlist", "input": {}}

```

`data` must not contain a raw newline, which is why it's one `json.dumps` (that escapes newlines inside strings). Response headers: `Content-Type: text/event-stream`, `Cache-Control: no-cache`, and `X-Accel-Buffering: no` so a proxy like nginx doesn't hold the stream back until it ends. Browsers read it with `EventSource` (GET only) or `fetch` plus a stream reader (what a POST needs).

### The status code goes first
An HTTP response is a status line, headers, then the body. A streaming response sends the first two as soon as it starts, so once the `conversation` event is out, the status is 200 for good. A failure later can only arrive as data: an `error` event. A client must also treat a stream that ends without `done` as a failure (a crash or a dropped connection sends no `error` event). That's why everything that can fail cleanly is checked before the stream starts.

### Async generators
A function with `async def` and `yield` returns an async iterator: nothing runs until someone iterates it with `async for`, and each `yield` hands one value over and pauses until the next one is asked for. It can't `return value`; the result travels in the last event (`Done(result)`). `async for x in inner(): yield x` passes another generator's values through. `StreamingResponse` iterates one and sends each value as it comes, so the loop only runs as fast as the client reads.

### A session that outlives the route
FastAPI calls the route function, which returns a `StreamingResponse`; Starlette iterates the generator *afterwards*. Anything the route opens and the stream uses must stay open until the stream ends. Here the route opens the session (to run the 404/409 checks) and hands it to the stream, which closes it in `finally`; if the checks fail, the route closes it itself, because the stream will never run.

### One client per app: connection pooling
An HTTP client keeps connections open and reuses them, skipping the TCP and TLS handshakes on later requests. A client per request throws that away. So the API builds one Anthropic, Cala and EDGAR client in the lifespan (startup), shares them across requests, and closes them at shutdown.

### Convert at the boundary
Data enters loose (JSON from Postgres: dicts) and is checked and converted once, where it enters (`ToolUseBlock.model_validate`); everything inside works with one typed shape. If every function accepted `ToolUseBlock | dict`, each would need an `isinstance` branch, mypy couldn't catch a typo in `block["nmae"]`, and bad data would fail deep inside instead of at the door. `model_validate` keeps every field the SDK knows; copying fields by hand silently drops new ones.

## Code map
| File | What it does | Why it exists / why this way |
|---|---|---|
| `backend/src/market_desk/agent/events.py` | `AssistantTurn`, `ToolResult`, `Done`: what the loop reports | The loop's output, independent of HTTP and the database |
| `backend/src/market_desk/agent/loop.py` | `stream_agent` / `stream_resume` yield events; `run_agent` / `resume_agent` drain them (`_final`); `_run_tool_timed`; `_as_tool_use` (exercise) | One loop for streaming and non-streaming callers |
| `backend/src/market_desk/conversations.py` | Create, load (client-scoped), check pending approval, `save_run` (messages with tokens, `tool_calls` rows); flush, never commit | Persistence in one place; the route owns the commit |
| `backend/src/market_desk/agent/services.py` | `AgentServices` and `services_from_settings` | Long-lived clients; `None` without keys |
| `backend/src/market_desk/api/chat.py` | `POST /chat`, `POST /chat/{id}/approvals`, checks before the stream, `_stream` (save, commit, `error`), SSE formatting | The HTTP side of the agent |
| `backend/src/market_desk/api/main.py` | The lifespan builds and closes the agent's clients; mounts the router | App-wide resources live in the lifespan |
| `backend/src/market_desk/config.py` | `anthropic_api_key` | Read from `.env`; optional |
| `backend/tests/fakes.py` | `FakeClaude` (scripted `MockTransport`, records requests, can fail with a status), `tool_call`, `answer` | Shared with task 6's loop tests |
| `backend/tests/test_chat.py` | Seven tests: whole stream and saved rows, history sent back, write waits + 409, approval, rollback on failure, 404s, 503 | The endpoint end to end, offline |

## Gotchas
!!! bug "(found) `ValueError: No tool_use blocks found` on every approval"
    **Symptom:** `test_an_approval_runs_the_call_and_finishes_the_run` failed: the stream sent `conversation`, then `error`.
    **Cause:** history reloaded from JSONB holds plain dicts; `isinstance(block, ToolUseBlock)` was False for all of them. (Predicted as note 1 in task 4.)
    **Fix:** `_as_tool_use`, which converts tool_use dicts with `ToolUseBlock.model_validate` (the guided exercise).
    **Lesson:** data that went through a database comes back in a different shape; test the round trip, not just the fresh objects.

!!! bug "(found) mypy: `event` has type `ToolResult`, got `AssistantTurn | ToolResult | Done`"
    **Cause:** in `stream_resume`, `event` was assigned a `ToolResult` in the tool loop; the final `async for event in stream_agent(...)` reused the name for any event.
    **Fix:** a new name, `next_event`.
    **Lesson:** a loop variable outlives its loop, and mypy fixes a variable's type at its first assignment.

!!! bug "(found) mypy: `dict()` of `str | Any` in `_to_json`"
    **Cause:** after `if isinstance(content, str): return`, mypy still saw `str` as possible inside `Iterable[Any]`, because a `str` is itself iterable.
    **Fix:** `cast(dict[str, Any], block)`: the non-model blocks are always dicts.
    **Lesson:** `str` is an `Iterable[str]`; narrowing a union that contains both can surprise you.

!!! bug "(open) Two approvals at once run the write twice"
    **Symptom:** none yet; found as a check question.
    **Cause:** both requests pass `has_pending_approval` before either commits (Postgres's default READ COMMITTED isolation), both run the tool and both save a result, leaving two `tool_result` messages after one `tool_use`, which the API then rejects.
    **Fix (to do):** lock the conversation row at the start of both routes (`.with_for_update()`), so the second request waits and then sees nothing pending (409). Or compare-and-set: `UPDATE ... WHERE status = 'pending_approval'` and check the row count.
    **Lesson:** a check followed by an action is a race unless something holds them together; in a database that's a row lock.

## Check questions
??? question "Claude returns a 500 mid-run. Why does the test see a 200, and how does a browser notice the failure?"
    The status line and headers left with the first event (`conversation`), so the status was fixed at 200 before Claude was even called. The browser reads the events: an `error` event, or a stream that ends without `done` (a crash or dropped connection sends nothing).

??? question "Two tabs approve the same pending `add_to_watchlist` at the same moment. What happens, and what stops it?"
    Both pass `has_pending_approval` (neither has committed, and READ COMMITTED only shows committed rows). Both run the tool and call Claude (paid twice) and both commit, leaving two `tool_result` messages after one `tool_use`: the API rejects that history, so the conversation is broken. A row lock held until commit stops it: `SELECT ... FOR UPDATE` on the conversation, or a compare-and-set `UPDATE ... WHERE status = 'pending_approval'` that the second request finds matching 0 rows. Recorded above as an open gotcha.

## Guided exercise
**Task (fix a bug, with a failing test):** make `stream_resume` find `tool_use` blocks whether they're SDK objects (fresh) or dicts (reloaded from Postgres), without changing `_run_tool` or `_is_write`. Acceptance: `test_an_approval_runs_the_call_and_finishes_the_run` passes, `make check` green, no new `type: ignore`.

**Outcome:** done with all three hints: `_as_tool_use(block)` returns the block if it's a `ToolUseBlock`, converts a dict whose `type` is `tool_use`, and returns `None` otherwise; `stream_resume` keeps the non-`None` results. 128 tests pass.

**What I got wrong:** the first version built the block field by field (`ToolUseBlock(id=block.get("id"), ...)`), which silently drops any field the SDK adds and gives a vague error for a missing one; changed to `ToolUseBlock.model_validate(block)` after review. The follow-up questions (why `.get("type")`, what iterating a string gives, why convert instead of accepting dicts) were answered by Claude, not me: worth re-reading.

**Lesson:** convert at the boundary, and let the model's own validation do it: `model_validate` keeps the SDK as the single definition of the shape. `.get` while sorting blocks (any block may lack a key), strict while building one.

## Explain it in 2 minutes
The chat endpoint runs the agent loop and streams what it does over Server-Sent Events: a long-lived HTTP response where each message is an event name and a line of JSON. The loop itself became an async generator that yields an event per step (Claude's turn, each tool result, and a final `Done` with the result), and the route turns those into SSE, so the loop knows nothing about HTTP. Because the status code goes out with the first byte, everything that can fail cleanly is checked first: unknown client or conversation is a 404, a conversation waiting for approval is a 409. After that, a failure can only be an `error` event. The whole request is one unit of work: messages, tool calls and tool writes are committed together when the run finishes, or all rolled back, so the stored history is always valid to send back to Claude. Write tools pause the run; a second endpoint takes the human's decisions and streams the rest. History reloaded from Postgres comes back as dicts, so it's converted to the SDK's types at the boundary.
