---
tags:
  - agents
  - security
  - postgres
---

# 4. Human confirmation for write tools

**Sprint 2** · **Date:** 2026-10-29 · **Plan item:** Human confirmation for write tools (the agent proposes, the API waits for approval)

## What and why
When Claude asks for a write tool (`add_to_watchlist`, `remove_from_watchlist`), `run_agent` stops before running anything and returns `status="awaiting_approval"` with the proposed calls. A human approves or rejects each call by its `tool_use_id`; `resume_agent` runs the approved ones, answers the rejected ones with an error result, and continues the loop. Writes change a client's data, so a person decides, and code enforces it. Along the way, a bug from Sprint 1 surfaced and was fixed first: the watchlist functions committed the session themselves (PR #18).

## Decisions
| Date | Decision | Why | Alternatives considered | ADR |
|---|---|---|---|---|
| 2026-10-29 | Pause and resume from the message list: return early with the pending calls, resume later with decisions | The Claude API is stateless, so `messages` already holds everything needed to continue; nothing waits in memory, and (once task 5 stores messages) a pause survives a restart | Ask in text ("shall I?"), which isn't enforced and a prompt injection can skip; `await` an approval inside the tool (holds a request open, lost on restart) | — |
| 2026-10-29 | A turn with any write pauses as a whole; reads run with the approved writes on resume | All results go back in one message, so running reads early means storing half a turn; reads are cheap | Run reads now, store their results until resume | — |
| 2026-10-29 | Decisions keyed by `tool_use_id`, not tool name | Two calls to the same tool in one turn ("add MSFT", "add GOOG") need separate answers | Key by name (all-or-nothing per tool) | — |
| 2026-10-29 | Decisions must match the turn's write calls exactly: a missing one or an extra one (an older turn's id, a read tool's id) raises `ValueError` before anything runs, naming every offending id | A silently ignored approval lets a reviewer believe they decided something they didn't; set differences find all offenders at once | Ignore extra decisions; report only the first bad id | — |
| 2026-10-29 | A rejected write gets `is_error: true` with "The user declined this action. Don't retry it unless the user asks again." | The model must know the action didn't happen, and not try it again on its own | A plain result (the model might say it's done); dropping the call (the API rejects a `tool_use` without its result) | — |
| 2026-10-29 | `_is_write(block)`: a known tool that writes; a made-up name isn't a write | One definition used in three places (pause, decision check, resume); an unknown tool goes to `_run_tool` and gets the normal error result | Repeat `TOOLS[name].writes` inline (crashed on a made-up name) | — |
| 2026-10-29 | Scope: the loop's pause and resume only; storing conversations, `tool_calls` rows and the approval endpoint come with `/chat` (task 5) | Those need persisted messages; doing them here would swallow half of task 5 | Build the endpoint now | — |
| 2026-10-29 | Watchlist functions flush and the session's owner commits (PR #18) | A commit inside a tool committed the whole run mid-way and escaped the tool's savepoint | Keep the commit (nothing in the loop can undo it) | — |

## Concepts

### Human in the loop: interrupt and resume
Some actions shouldn't run on a model's say-so. The loop splits a run in two: `run_agent` returns as soon as Claude proposes a write, and `resume_agent` picks up once a person has decided. Between the two, the state is just the message list, which ends on Claude's turn with its `tool_use` blocks. That's valid as long as the results are sent before the next model call. LangGraph calls the same idea an *interrupt* with a *checkpointer* (task 7).

### Enforce in code, not in the prompt
"Ask the user before adding" in a system prompt is a request the model may ignore, or be talked out of by injected text in a filing. The gate in `run_agent` checks `Tool.writes`, which the model can't change: a write tool never runs without a decision, whatever the model says.

### Unit of work: who commits
A session is a unit of work, and whoever opens it commits or rolls it back: the CLI command, the job, the `/chat` request. Library functions add and `flush()`: the SQL runs inside the open transaction, so constraint errors surface where a savepoint can still undo them, but nothing is permanent. A function that commits can't be part of a bigger unit of work: inside the agent, it saved every earlier tool's changes and ended the outer transaction from inside the tool's savepoint.

### flush vs commit
`flush()` sends pending INSERTs, UPDATEs and DELETEs to the database inside the current transaction; other connections don't see them, and a rollback removes them. `commit()` makes them permanent and visible. Tests and savepoints work with flushed data; only the owner of the unit of work commits.

### Validate approvals both ways
An approval request is input like any other. Compare it with what is actually pending, in both directions: every pending write needs a decision (`write_ids - decisions.keys()`), and every decision must match a pending write (`decisions.keys() - write_ids`). Set differences give every offending id at once, and `dict.keys()` already supports them.

### `dict.get` for a safe lookup
`TOOLS[name]` raises `KeyError` for a missing name; `TOOLS.get(name)` returns `None`. When the key comes from the model, a missing one is expected, so `_is_write` uses `.get` and checks for `None`.

## Code map
| File | What it does | Why it exists / why this way |
|---|---|---|
| `backend/src/market_desk/agent/loop.py` | `run_agent` pauses on write calls (`awaiting_approval`, `pending`); `resume_agent` validates decisions, runs reads and approved writes, declines the rest, continues the loop; `_is_write`; `DECLINED` | The approval gate lives in the loop, so every caller (`/chat`, the dashboard, LangGraph's comparison) gets it |
| `backend/src/market_desk/watchlist.py` | `add_to_watchlist` / `remove_from_watchlist` flush instead of commit; the CLI commits | PR #18: the caller owns the transaction |
| `backend/tests/test_watchlist.py` | `test_add_and_remove_leave_the_commit_to_the_caller` | Proves a rollback after add or remove leaves the table unchanged; red before the fix |

## Gotchas
!!! bug "(found) A test run committed MSFT to the dev database"
    **Symptom:** after the acceptance script (which rolls back at the end), `watchlists` in the dev DB held MSFT; later runs saw it as "already watched".
    **Cause:** `add_to_watchlist` called `session.commit()` itself. Inside the agent that commits the whole run mid-way, and a commit inside `begin_nested()` commits the outer transaction too, so neither the savepoint nor the caller's rollback can undo it. The [task 3 exercise](03-agent-loop.md#guided-exercise) didn't show it, because EDGAR failed before the commit line.
    **Fix:** flush instead of commit; the CLI commits (PR #18). The leaked row was deleted.
    **Lesson:** a savepoint only protects work that hasn't been committed; library code shouldn't commit.

!!! bug "(review) Decisions looked up by tool name: `add_to_watchlist does not have one`"
    **Cause:** the checks used `block.name` as the key into `decisions`, which is keyed by `tool_use_id`.
    **Fix:** `block.id`.
    **Lesson:** a tool name identifies a tool; an id identifies one call.

!!! bug "(review) `KeyError: 'toolu_list'` in a turn with a read and a write"
    **Cause:** step 3 read `TOOLS[tool_name]`, where `tool_name` was left over from step 2's loop (the last block's name), so `list_watchlist` was treated as a write.
    **Fix:** `block.name`, then `_is_write(block)`.
    **Lesson:** a `for` loop's variable outlives the loop; same class as Sprint 1's [leftover loop variable](../sprint-1/07-filing-check.md#gotchas).

!!! bug "(review) `KeyError: 'get_stock_price'`: a write plus a made-up tool crashed the resume"
    **Cause:** `TOOLS[block.name].writes` on a name the model invented; the original scenarios never combined a write with an unknown tool.
    **Fix:** `_is_write` uses `TOOLS.get(...)`; unknown tools go to `_run_tool`, which answers with an error result.
    **Lesson:** input from the model can be wrong in combinations, not just alone; test the mixes.

!!! bug "(found) Two false results from my acceptance script"
    **Cause:** "ends on the assistant turn" passed by accident (the final answer is also an assistant message), and the results were read from `messages[-2]` instead of `[-1]`, which made approve and reject look broken.
    **Fix:** check for the `tool_use` blocks; read `[-1]`.
    **Lesson:** a check that can't fail proves nothing; when a test fails, suspect the test too.

## Check questions
??? question "Claude asks to add MSFT and GOOG in one turn; the reviewer approves MSFT and rejects GOOG. What does Claude receive? Why can't decisions be keyed by tool name?"
    One user message with two `tool_result` blocks, in the order Claude asked, each matched by `tool_use_id`: MSFT's real result, then GOOG's `DECLINED` with `is_error: true`. Keyed by name, `{"add_to_watchlist": True}` would approve both or neither.

??? question "Before the fix, `add_to_watchlist` committed. A run approves MSFT, then `/chat` fails and rolls back. What's in the database?"
    MSFT, plus anything earlier tools had pending in the session: the commit is final, and because it ran inside the tool's savepoint it ended the outer transaction too, leaving the rollback nothing to undo.

## Guided exercise
**Task (extend a feature):** `resume_agent` checked that every pending write has a decision, but silently ignored decisions for ids that aren't pending (an older turn's tool call, a stale browser tab). Raise `ValueError` for those before anything runs, naming the id. Acceptance: a new "stale decision" scenario in the acceptance script, red before.

**Outcome:** done; all 45 checks pass. Then refactored with Claude to set differences (`write_ids - decisions.keys()` and the reverse), so both errors name every offending id.

**What I got wrong:** nothing in the logic; the first version reported only the first bad id.

**Lesson:** validate an approval against what's pending in both directions. Decisions for read tools also raise, deliberately: a read always runs, so "rejecting" it would be silently ignored and mislead the reviewer.

## Explain it in 2 minutes
Write tools never run on the model's word. When Claude asks to add or remove a watchlist entry, the loop returns early with the proposed calls instead of running them. Because the API is stateless, the conversation itself is the saved state: it ends on Claude's request, and nothing waits in memory. A person approves or rejects each call by its id; resuming checks the decisions match exactly what's pending, runs the approved calls with the arguments Claude proposed, answers rejected ones with an error so Claude knows they didn't happen, and continues the normal loop. The gate is in code, keyed on a flag the model can't touch, so a prompt injection can't talk its way past it. Building it exposed a transaction bug: library functions were committing on their own, which a savepoint can't undo; now only the owner of the session commits.
