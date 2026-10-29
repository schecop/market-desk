---
tags:
  - agents
  - errors
  - postgres
---

# 3. The agent loop

**Sprint 2** · **Date:** 2026-10-29 · **Plan item:** `agent/loop.py`: hand-written tool-use loop with step limit, error handling, parallel tool calls, token/cost accounting

## What and why
`agent/loop.py`: `run_agent` sends the conversation and the five tool definitions to Claude (`claude-sonnet-5-5`), runs the tools Claude asks for, sends the results back and repeats until Claude answers or a step limit stops it. This loop *is* the agent: `/chat`, human confirmation, LangGraph and MCP all build on it. Claude wrote the basic loop; I added the step limit, tool errors as results and token/cost accounting.

## Decisions
| Date | Decision | Why | Alternatives considered | ADR |
|---|---|---|---|---|
| 2026-10-28 | Hand-written loop on `messages.create`, with the `anthropic` SDK 2.x | The loop is the lesson; the SDK is built on `httpx2`, so it's tested offline with `MockTransport` like our other clients (ADR-0003) | The SDK's Tool Runner (writes the loop for you); LangGraph comes in task 7 as the framework comparison | The loop-vs-LangGraph ADR comes with task 8 |
| 2026-10-28 | The loop stores nothing: it extends the message list it gets and returns an `AgentResult`; the caller saves the conversation and commits | Easy to test, and one place (task 5) owns the transaction | The loop writes `messages` and `tool_calls` rows itself | — |
| 2026-10-28 | A savepoint per tool call (`session.begin_nested()`) | A tool that fails halfway is rolled back on its own; earlier tools' writes stay. Closes the open question from [task 1](01-agent-tools.md#gotchas) | Roll back the whole session on any error (loses good earlier writes); each tool cleans up itself (easy to forget) | — |
| 2026-10-28 | Tools run one after another; all results go back in one user message | Tools share one SQLAlchemy session, which two coroutines can't use at once; one message keeps Claude making parallel calls | `asyncio.gather` with a session per tool (later, if latency matters) | — |
| 2026-10-29 | Expected failures (`ValidationError`, `ToolError`, `CalaError`, `EdgarError`, unknown tool) become `is_error` results; anything else propagates | The model can react to a bad argument or a down service; it can't fix our bugs, and a caught bug would be hidden | Catch `Exception` (hides bugs, hands the model an error it can't act on) | — |
| 2026-10-29 | The unknown-tool check runs before the lookup and lists the available tools | A `KeyError` raised inside a tool would otherwise be reported as "unknown tool"; the list tells the model what to do instead | Catch `KeyError` around the lookup | — |
| 2026-10-29 | `max_steps=8` by default; `max_steps < 1` raises `ValueError` | A runaway agent costs money; 0 steps is a programmer mistake, not something for the model | No limit; clamp silently to 1 | — |
| 2026-10-29 | Cost as `@property` computed from the token counts, prices as constants next to `MODEL` | A stored cost could disagree with the tokens; constants make a price change one line | Store the cost; hard-code prices in the loop | — |
| 2026-10-28 | `refusal` is just a result status; no server-side fallback model yet | Keep the first version small | The `fallbacks: "default"` beta, which retries a refused request on another model | — |

## Concepts

### The agent loop and stop_reason
The Claude API is stateless and never runs code. Each call gets the whole conversation plus the tool definitions; the reply's `stop_reason` says what happens next. `tool_use` means "run these tools and call me again"; every other reason ends the run: `end_turn` (an answer), `max_tokens` (cut off by the per-response limit), `refusal` (a safety classifier declined). So the loop is a small state machine with one way to continue:

```python
while steps < max_steps:
    response = await client.messages.create(..., messages=messages)
    messages.append({"role": "assistant", "content": response.content})
    if response.stop_reason != "tool_use":
        return ...                      # done, max_tokens, refusal
    messages.append({"role": "user", "content": [tool results]})
```

### Append the whole assistant turn
`response.content` goes back into the history unchanged, not just its text. It holds the `tool_use` blocks that the next `tool_result` blocks answer (matched by `tool_use_id`), and the model's thinking blocks, which Sonnet 5.5 produces by default and which the API rejects if they are edited or dropped.

### Tool errors are data
A failed tool returns a `tool_result` with `is_error: True` and a message the model can act on ("Tool X is not available. Available tools are: ..."). The model then retries, picks another tool or tells the user. Raising instead would end the request for something the model could have handled. The line to draw: errors the model can react to (bad arguments, an unknown ticker, a service that's down) become results; bugs in our code propagate, get fixed at the root, and the caller returns a 500.

### Parallel tool calls
One assistant turn can contain several `tool_use` blocks. Their results all go back in **one** user message, in any order, each tied to its call by `tool_use_id`. Sending them in separate messages makes Claude stop making parallel calls. Running them concurrently is a separate choice: here they run one after another because they share a database session.

### Step limits
A model can keep calling tools forever: a tool that always fails, a question it can't settle. `max_steps` caps the model calls per run and returns `status="step_limit"`, so the caller can tell "Claude finished" from "we stopped it". The history stays valid: the limit is checked after the tool results are appended, so every `tool_use` has its `tool_result`, and a follow-up question (or another `run_agent` call) continues from there.

### Token and cost accounting
Every response reports `usage.input_tokens` and `usage.output_tokens`. Input grows each step, because each call re-sends the whole history, including every tool result: that's why tools return compact JSON (`exclude_none`). Cost = tokens × price ÷ 1,000,000; Sonnet 5.5 is $2 per million input tokens and $10 per million output tokens. Computing cost in a `@property` means it can never disagree with the token counts.

### Savepoints
A savepoint is a checkpoint inside a transaction: `SAVEPOINT x` ... `ROLLBACK TO SAVEPOINT x` undoes only the work since the checkpoint, and the outer transaction carries on. In SQLAlchemy, `with session.begin_nested():` opens one, releases it if the block succeeds, and rolls back to it (then re-raises) if the block raises. Here it wraps each tool call: `add_to_watchlist` adds the entry, then `list_filings` fails; the savepoint removes the entry, so a later commit can't save it without its baseline. Proven in the guided exercise below. Caveat found in [task 4](04-write-confirmation.md#unit-of-work-who-commits): a savepoint only protects uncommitted work, so code inside it must not commit.

### Fail fast on bad arguments
Reject invalid input where it enters, with a message that names the problem: `raise ValueError(f"max_steps should be greater than 0, got {max_steps}")` on the first line of `run_agent`, instead of an `UnboundLocalError` about `response` at the end of it.

### Commas make tuples
In Python, commas build a tuple, so `tokens * price / 1, 000, 000` is `(tokens * price / 1, 0, 0)`; `000` is a valid way to write zero. Digits are grouped with underscores: `1_000_000`. mypy caught it because the property was annotated `-> float`.

## Code map
| File | What it does | Why it exists / why this way |
|---|---|---|
| `backend/pyproject.toml`, `uv.lock` | Adds `anthropic>=2.3.0` | The official SDK; 2.x is built on `httpx2`, like our clients |
| `backend/src/market_desk/agent/__init__.py` | Makes `agent/` a package | The loop now; the LangGraph version (task 7) next to it |
| `backend/src/market_desk/agent/loop.py` | `run_agent`, `AgentResult`, `_run_tool`, the model, prices and system prompt | The agent; protocol details (whole assistant turn, one results message, savepoints) in one place |

## Gotchas
!!! bug "(review) `TypeError: Object of type ValidationError is not JSON serializable`"
    **Cause:** the error `tool_result` had `"content": err`, the exception object, where the API expects a string.
    **Fix:** `"content": str(err)`.
    **Lesson:** mypy flagged it first (`TypedDict item "content" has type "str | Iterable[...]"`): types catch what tests miss.

!!! bug "(review) `KeyError: 'get_stock_price'` crashed the loop"
    **Cause:** `TOOLS[block.name]` for a tool name the model made up; `KeyError` wasn't among the caught errors.
    **Fix:** check `block.name not in TOOLS` before the lookup and return an `is_error` result listing the available tools.
    **Lesson:** the model generates tool names too; anything it sends is input to validate.

!!! bug "(review) `UnboundLocalError: cannot access local variable 'response'` with `max_steps=0`"
    **Cause:** the final `return` reads `response`, which only exists if the loop ran at least once.
    **Fix:** `if max_steps < 1: raise ValueError(...)` at the top.
    **Lesson:** fail fast where the bad value enters.

!!! bug "(review) The cost was `(4000.0, 0, 0)` instead of `0.004`"
    **Cause:** `/ 1, 000, 000`: commas build a tuple.
    **Fix:** `/ 1_000_000`.
    **Lesson:** mypy caught it (`got "tuple[float, int, int]", expected "float"`); the scenario script didn't, because it never read the cost.

## Check questions
??? question "A tool has a real bug (an `AttributeError`) and the loop doesn't catch it. What happens to the savepoint, the loop and the request?"
    The savepoint rolls back that tool's writes and re-raises; the exception leaves `run_agent`, and `/chat` must return a 500 and roll back the whole session. Catching it would hand the model an error it can't fix and hide the bug, which should be fixed at its root. Also: `messages` now ends on a `tool_use` with no `tool_result`, which the API rejects with a 400, so never save that history without adding an error result first.

??? question "The step limit hits right after the tools ran. What is the last message, and why does it matter?"
    A user message with the tool results. The history is valid (every `tool_use` has its `tool_result`) and the results aren't lost: a follow-up question, or calling `run_agent` again, continues from them instead of repeating the tool calls.

## Guided exercise
**Task (break something on purpose, predict first):** a script with a fake Claude that calls `add_to_watchlist("MSFT")` and a fake EDGAR that finds the company, then fails on `list_filings` with a 503. Predict, then run, with and without the savepoint: does the run return, and is MSFT in the session afterwards?

**Outcome:** prediction right. Both runs end `done` and the model gets the same `is_error` result ("EDGAR returned 503"). With the savepoint, MSFT is gone from the session; without it, it's still there, pending.

**What I got wrong:** nothing. (The exercise statement first said the loop would crash in both cases; it doesn't, because `EdgarServerError` is an `EdgarError`, which the loop catches.)

**Lesson:** from the outside the two runs are identical; only the database state differs. The savepoint is what stops `/chat`'s commit from saving MSFT without its `seen_filings` baseline, which would alert on every 10-K Microsoft ever filed.

## Explain it in 2 minutes
An agent is a loop around a stateless API. I send Claude the conversation and my tools' definitions; if it answers, I'm done; if it asks for tools, I run them, append the results and call it again. Three things make it production-shaped. First, limits: a step cap so it can't loop forever, and token counts on every response, because each step re-sends the whole history, so cost grows with every tool result. Second, errors are data: a bad argument or a down service becomes a tool result marked as an error, so the model can recover, while bugs in my own code still raise. Third, state: each tool call runs inside a database savepoint, so a tool that fails halfway leaves nothing behind, and the caller decides when to commit. Several tool calls in one turn are answered in one message, matched by id.
