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
The agent gets its first real caller. `POST /chat` takes a message, reloads the conversation from Postgres, runs the loop and streams what happens (tool calls, results, the answer) as Server-Sent Events. Then it saves the run and commits once. `POST /chat/{id}/approvals` resumes a run that's waiting for a human. The work came in two steps: **5a** streams one event per loop step (our API to the browser); **5b** also streams from Claude to our API with `messages.stream()`, so the answer reaches the browser word by word. Then a row lock closed a race between two requests for the same conversation.

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
| 2026-10-31 | 5b: `messages.stream()` with `text_stream` for the deltas and `get_final_message()` for the rest of the loop | The loop after the call doesn't change: `get_final_message()` returns the same `Message` as `create()`; `async with` closes Claude's connection if we stop early | Iterate the raw stream events (partial tool JSON, thinking: not needed yet); `create(stream=True)` and assemble the message ourselves | — |
| 2026-10-31 | `text_delta` events replace `text`; `done.answer` keeps the full text | Sending both would deliver the answer twice | Keep `text` as a final complete-block event | — |
| 2026-10-31 | Lock the conversation row (`SELECT ... FOR UPDATE`) in both routes, before the pending check | One lock closes both races (two approvals, two messages) and only blocks requests for the same conversation | Compare-and-set on `tool_calls` (only covers approvals, reshapes `save_run`); `NOWAIT` with an immediate 409 (revisit in Sprint 4, with the UI) | — |
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

### Streaming from Claude: nested streams
Claude's API streams too: `message_start`, then per content block `content_block_start`, `content_block_delta` (text pieces, or a tool's arguments as partial JSON), `content_block_stop`, then `message_delta` (stop reason, final usage) and `message_stop`. The SDK parses them: `stream.text_stream` yields just the text, and `get_final_message()` assembles the whole `Message`. So there are two streams in a chain, Claude to our API and our API to the browser, and each piece is passed on as it arrives. If the browser disconnects, Starlette cancels our generator with `CancelledError` (a `BaseException`, so `except Exception` doesn't catch it): `finally` closes the session without committing, and `async with` closes Claude's connection, which stops the tokens being generated and billed.

### Variance: why `list[Child]` isn't a `list[Parent]`
`get_final_message()` returns `ParsedTextBlock`s, a subclass of `TextBlock`, and mypy refused a `list[ParsedTextBlock | ...]` where `list[TextBlock | ...]` was expected. A list can be written to: if it were accepted, code could `.append()` a plain `TextBlock` into a list that should only hold `ParsedTextBlock`s. So `list` is *invariant*. `Sequence` is read-only, so it's *covariant*: a `Sequence[Child]` is a `Sequence[Parent]`. Rule: when you only read, ask for the weakest type you need (`Sequence`, `Iterable`, `Mapping`).

### Row locks: `SELECT ... FOR UPDATE`
`FOR UPDATE` locks the selected rows until the transaction ends. Another transaction that tries to lock (or update, or delete) the same row waits; one that locks a different row doesn't. That turns a check-then-act sequence into one that can't interleave: the second request waits at the lock, then its check sees the first request's committed result. `FOR UPDATE NOWAIT` fails at once ("could not obtain lock on row") instead of waiting: useful to answer "busy" fast.

### MVCC: readers don't wait for locks
Postgres keeps several versions of a row: a plain `SELECT` reads the last committed version and never waits on a row lock. Only lockers and writers wait. So a lock protects a check only if *every* writer takes it; a route that reads without `FOR UPDATE` would see the old state and race again.

### A failed statement poisons the transaction
In Postgres, once any statement inside a transaction fails, every later one is refused ("current transaction is aborted, commands ignored until end of transaction block") until `ROLLBACK`. psql shows it in the prompt: `=#` no transaction, `=*#` inside one, `=!#` inside a failed one. A savepoint (`SAVEPOINT s` / `ROLLBACK TO s`, `begin_nested()` in SQLAlchemy) undoes just the failed part, which is why `_run_tool` uses one: a failing tool would otherwise poison the whole run.

## Code map
| File | What it does | Why it exists / why this way |
|---|---|---|
| `backend/src/market_desk/agent/events.py` | `AssistantTurn` (content as a `Sequence`), `ToolResult`, `TextDelta` (5b, written by Pablo), `Done`: what the loop reports | The loop's output, independent of HTTP and the database |
| `backend/src/market_desk/agent/loop.py` | `stream_agent` / `stream_resume` yield events; `run_agent` / `resume_agent` drain them (`_final`); `_run_tool_timed`; `_as_tool_use` (exercise); 5b: `messages.stream()`, a `TextDelta` per text piece (written by Pablo) | One loop for streaming and non-streaming callers |
| `backend/src/market_desk/conversations.py` | Create, load (client-scoped, optionally locked `FOR UPDATE`), check pending approval, `save_run` (messages with tokens, `tool_calls` rows); flush, never commit | Persistence in one place; the route owns the commit |
| `backend/src/market_desk/agent/services.py` | `AgentServices` and `services_from_settings` | Long-lived clients; `None` without keys |
| `backend/src/market_desk/api/chat.py` | `POST /chat`, `POST /chat/{id}/approvals`, the conversation locked before the checks, `_stream` (save, commit, `error`), SSE formatting (`text_delta` in 5b) | The HTTP side of the agent |
| `backend/src/market_desk/api/main.py` | The lifespan builds and closes the agent's clients; mounts the router | App-wide resources live in the lifespan |
| `backend/src/market_desk/config.py` | `anthropic_api_key` | Read from `.env`; optional |
| `backend/tests/fakes.py` | `FakeClaude` (scripted `MockTransport`, records requests, can fail with a status, answers `"stream": true` with real SSE via `as_sse`), `tool_call`, `answer` | Shared with task 6's loop tests |
| `backend/tests/test_conversations.py` | `test_get_conversation_locks_the_row_only_when_asked`: records the SQL sent (`before_cursor_execute`) | Proves `FOR UPDATE` is sent, without a fragile two-thread race test |
| `backend/tests/test_chat.py` | Eight tests (5b adds: deltas join up to the answer, `stream: true` sent): whole stream and saved rows, history sent back, write waits + 409, approval, rollback on failure, 404s, 503 | The endpoint end to end, offline |

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

!!! bug "(fixed) Two approvals at once run the write twice"
    **Symptom:** none seen; found as a check question.
    **Cause:** both requests pass `has_pending_approval` before either commits (Postgres's default READ COMMITTED isolation), both run the tool and both save a result, leaving two `tool_result` messages after one `tool_use`, which the API then rejects.
    **Fix:** both routes load the conversation with `get_conversation(..., lock=True)` (`SELECT ... FOR UPDATE`) before the pending check; the second request waits, then sees nothing pending (409). Shown live in the [psql exercise](#guided-exercise).
    **Lesson:** a check followed by an action is a race unless something holds them together; in a database that's a row lock.

!!! bug "(found) mypy: `list[ParsedTextBlock | ...]` is not `list[TextBlock | ...]`"
    **Cause:** `get_final_message()` returns parsed blocks (subclasses); `AssistantTurn.content` was a `list`, which is invariant.
    **Fix:** `Sequence[ContentBlock]`: read-only, so covariant.
    **Lesson:** see [Variance](#variance-why-listchild-isnt-a-listparent).

!!! bug "(found) psql: `null value in column \"id\"` inserting a conversation by hand"
    **Cause:** the UUID default is `default=uuid.uuid4` in the model: SQLAlchemy fills it in Python before the INSERT. The table has no default, so raw SQL gets none. (`created_at` worked: it's a `server_default`, which lives in the table.)
    **Fix:** `INSERT INTO conversations (id, client_id) SELECT gen_random_uuid(), ...`.
    **Lesson:** `default=` only helps code that goes through SQLAlchemy; `server_default=` helps everyone, psql and migrations included.

!!! bug "(found) psql: `current transaction is aborted, commands ignored until end of transaction block`"
    **Cause:** an earlier statement in the same `BEGIN` block had failed; the prompt showed `=!#`.
    **Fix:** `ROLLBACK;` (which also undid anything else in that block), then start again.
    **Lesson:** see [A failed statement poisons the transaction](#a-failed-statement-poisons-the-transaction).

!!! bug "(found) psql: the second `FOR UPDATE` didn't wait"
    **Cause:** the two windows were locking two different conversations (the INSERT had been re-run and one window kept the new id). Row locks are per row.
    **Fix:** the same id in both windows; check the holder with `pg_stat_activity` (`idle in transaction` means a transaction is open, `idle` means it isn't) and the `=*#` prompt.
    **Lesson:** when a lock doesn't block, first check it's the same row and that the holder's transaction is still open.

## Check questions
??? question "Claude returns a 500 mid-run. Why does the test see a 200, and how does a browser notice the failure?"
    The status line and headers left with the first event (`conversation`), so the status was fixed at 200 before Claude was even called. The browser reads the events: an `error` event, or a stream that ends without `done` (a crash or dropped connection sends nothing).

??? question "Two tabs approve the same pending `add_to_watchlist` at the same moment. What happens, and what stops it?"
    Both pass `has_pending_approval` (neither has committed, and READ COMMITTED only shows committed rows). Both run the tool and call Claude (paid twice) and both commit, leaving two `tool_result` messages after one `tool_use`: the API rejects that history, so the conversation is broken. A row lock held until commit stops it: `SELECT ... FOR UPDATE` on the conversation, or a compare-and-set `UPDATE ... WHERE status = 'pending_approval'` that the second request finds matching 0 rows. Recorded above as an open gotcha.

??? question "The `text_delta` events reach the browser before `save_run` commits. If the commit fails, what has the user seen?"
    Possibly the whole answer: the commit runs after every delta was sent. Then `error` says nothing was saved, so the next message goes to a Claude that never saw that answer. The UI must mark or remove the unsaved answer when `error` arrives (Sprint 4).

??? question "`run_agent` now goes through `messages.stream()` too. A problem?"
    No: it drains the events until `Done`. Same tokens, same price, a little parsing overhead; one code path to test, and a long generation doesn't sit silent on one HTTP response, where proxy idle timeouts bite.

??? question "Why didn't the plain SELECT wait while the other window held `FOR UPDATE`, and what does it mean for the API?"
    MVCC: plain reads see the last committed version and never wait on row locks; only lockers and writers do. So the lock protects `has_pending_approval` only if every route that writes takes it first.

## Guided exercise
**Task (fix a bug, with a failing test):** make `stream_resume` find `tool_use` blocks whether they're SDK objects (fresh) or dicts (reloaded from Postgres), without changing `_run_tool` or `_is_write`. Acceptance: `test_an_approval_runs_the_call_and_finishes_the_run` passes, `make check` green, no new `type: ignore`.

**Outcome:** done with all three hints: `_as_tool_use(block)` returns the block if it's a `ToolUseBlock`, converts a dict whose `type` is `tool_use`, and returns `None` otherwise; `stream_resume` keeps the non-`None` results. 128 tests pass.

**What I got wrong:** the first version built the block field by field (`ToolUseBlock(id=block.get("id"), ...)`), which silently drops any field the SDK adds and gives a vague error for a missing one; changed to `ToolUseBlock.model_validate(block)` after review. The follow-up questions (why `.get("type")`, what iterating a string gives, why convert instead of accepting dicts) were answered by Claude, not me: worth re-reading.

**Lesson (5a):** convert at the boundary, and let the model's own validation do it: `model_validate` keeps the SDK as the single definition of the shape. `.get` while sorting blocks (any block may lack a key), strict while building one.

**Task 5b (core, written by me):** swap `messages.create` for `messages.stream()` in `stream_agent`, yield a `TextDelta` per text piece, add the event and its `text_delta` SSE mapping. Acceptance: three tests Claude wrote first (red before), `make check` green.

**Outcome:** the tests passed on the first try; `make check` then failed on one mypy error (list invariance, see Gotchas), which Claude fixed on request with `Sequence`.

**Lesson (5b):** when the new call's result has the same shape (`get_final_message()` vs `create()`), the rest of the loop doesn't change: the swap is six lines.

**Task (row locks, predict and verify in two psql windows):** lock a conversation with `FOR UPDATE` in one session, try again from another, commit, then try a plain `SELECT` and `NOWAIT`.

**Outcome:** after three detours (the Python-side UUID default, an aborted transaction, two different ids: all in Gotchas), the second `FOR UPDATE` waited until the first committed, the plain `SELECT` returned at once, and `NOWAIT` failed with "could not obtain lock on row".

**What I got wrong:** I described `NOWAIT` as bypassing the lock; it doesn't, it fails instead of waiting.

**Lesson:** a lock serialises only the transactions that take it; readers see the last committed version (MVCC). Check the prompt (`=*#`) and `pg_stat_activity` before trusting a lock test.

## Explain it in 2 minutes
The chat endpoint runs the agent loop and streams what it does over Server-Sent Events: a long-lived HTTP response where each message is an event name and a line of JSON. The loop itself became an async generator that yields an event per step (Claude's turn, each tool result, and a final `Done` with the result), and the route turns those into SSE, so the loop knows nothing about HTTP. Because the status code goes out with the first byte, everything that can fail cleanly is checked first: unknown client or conversation is a 404, a conversation waiting for approval is a 409. After that, a failure can only be an `error` event. The whole request is one unit of work: messages, tool calls and tool writes are committed together when the run finishes, or all rolled back, so the stored history is always valid to send back to Claude. Write tools pause the run; a second endpoint takes the human's decisions and streams the rest. History reloaded from Postgres comes back as dicts, so it's converted to the SDK's types at the boundary. Claude's reply is streamed too, so the answer reaches the browser word by word: two streams in a chain, and a browser disconnect cancels both. Finally, both routes lock the conversation row before checking for pending approvals, so two tabs can't approve the same write twice: the second one waits, then gets a 409.
