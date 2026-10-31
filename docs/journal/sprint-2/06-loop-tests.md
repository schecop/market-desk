---
tags:
  - agents
  - testing
---

# 6. Testing the loop deterministically

**Sprint 2** · **Date:** 2026-10-31 · **Plan item:** Tests: fake LLM responses to test the loop deterministically (tool call → result → answer; tool error; step limit hit)

## What and why
`backend/tests/test_loop.py` tests the agent loop on its own (`run_agent`, `stream_agent`, `resume_agent`), with no HTTP in between. Each test scripts Claude's replies with `FakeClaude`, runs the loop on the real tools, the fake SEC and the test database, and checks three things: what the loop **yielded or returned**, what it **sent back to Claude**, and what ended up in the **database**.

`test_chat.py` already covered the endpoint end to end. The loop's own rules had only been checked by throwaway scripts in task 3: tool errors returned as data, parallel results in one message, the step limit, token sums, declined writes. Now they're a contract that will catch a regression in the LangGraph version (task 7) or in any later change.

## Decisions
| Date | Decision | Why | Alternatives considered | ADR |
|---|---|---|---|---|
| 2026-10-31 | Fake Claude at the HTTP boundary (`FakeClaude` under the real SDK), not by mocking `client.messages.stream` | The real SDK still builds the request body and parses the stream, so the tests check what really goes over the wire. A mock returns whatever shape we assume, including shapes the SDK never produces | `unittest.mock` on the SDK method (simpler, but it tests our assumptions); recorded real responses, VCR-style (need live calls, cost money, break on every prompt change, against [ADR-0003](../../adr/0003-http-client-design.md)) | — |
| 2026-10-31 | Unexpected exceptions in a tool (bugs, not `ToolError`) propagate out of the loop; the tool's savepoint has already undone its writes | A bug shouldn't become a polite message to Claude, which would hide it. The route rolls the whole run back and sends an `error` event (task 5). Closes the open note from task 3 | Catch everything and return it as an error `tool_result` (hides bugs; the run "succeeds" with broken data) | — |
| 2026-10-31 | Script more replies than the step limit allows | A loop that made one call too many gets a reply, and the request count catches it. With exactly enough replies, the failure would be an unrelated `IndexError` from the empty script | Exactly `max_steps` replies (fails, but with a confusing error) | — |

## Concepts
### Test the contract, not the internals
A test should check what the code promises to the outside world: its inputs, outputs and side effects. It shouldn't check how the code gets there. For the loop, the contract is the events it yields, the `AgentResult`, the messages it sends to Claude (read from `claude.requests`, the real HTTP bodies) and the rows in the database. No test looks at private helpers like `_run_tool`. That's why the same tests could run against a rewritten loop (LangGraph, task 7) almost unchanged.

### Fakes vs mocks
A **fake** is a small working implementation that stands in for a real dependency: `FakeClaude` answers HTTP requests like the Messages API, from a script. A **mock** replaces an object and records how it was called (`mock.assert_called_with(...)`). Fakes test behaviour; mocks tend to test calls, and break when the code is refactored without any change in behaviour. Fake at the boundary you don't own (the network). Don't mock your own code.

### Arrange / act / assert
Each test has three parts. **Arrange**: build the inputs (Claude's scripted replies, the question). **Act**: call the one thing under test, once. **Assert**: check the results. When a test fails, it's then clear what was set up and what was checked. A test that acts several times usually wants to be two tests. The rejected-write test is the exception: pause, then resume, because the pause is the arrange step for the resume.

### Mutation testing
Mutation testing asks "do my tests fail when the code is wrong?" It plants a small bug (a mutant: `<` becomes `<=`, a line is deleted, an exception type is dropped), runs the tests, and checks that at least one fails. A mutant that survives points to behaviour no test guards. Tools like `mutmut` do it automatically; here it was done by hand as the guided exercise. Code coverage only says a line *ran*. Mutation testing says whether a test would *notice* if the line were wrong.

## Code map
| File | What it does | Why it exists / why this way |
|---|---|---|
| `backend/tests/test_loop.py` | 11 tests (15 cases with the parametrized ones) of the loop: happy path, tool error, unknown tool, parallel calls, step limit, `max_steps=0`, rejected write, mismatched decisions, a buggy tool, stop reason → status, text deltas | The loop's rules as a contract, with no HTTP in between |
| `ctx` fixture in `test_loop.py` | A `ToolContext` on the test database and the fake SEC, with Cala left as `None` | No test here calls Cala. If one does by mistake, it fails loudly instead of reaching the network |
| `collect`, `kinds`, `watched` helpers | Run a stream to the end; list event types without the text deltas; list the watchlist's tickers | `kinds` drops `TextDelta` because how many there are depends on how the fake splits text, which no test should depend on |

## Gotchas
!!! bug "mypy on one test file: `module is installed, but missing library stubs or py.typed marker`"
    **Cause:** `uv run mypy tests/test_loop.py` checks the file without the project's config (`files`, `mypy_path`), so it treats `market_desk` as an untyped third-party package.
    **Fix:** run `uv run mypy` with no arguments from `backend/` (what `make` does): it reads `pyproject.toml` and checks `src` and `tests` together.
    **Lesson:** run the tools the way the project runs them; a one-off invocation can report errors that aren't real.

!!! bug "A test copied from the worked example kept the example's assertions"
    **Symptom:** the first draft of the tool-error test expected the tool_result `'{"companies":[]}'`, which is `list_watchlist`'s output, for a `search_filings` call that fails.
    **Cause:** copying the example's shape also copied what it checks.
    **Fix:** assert what *this* scenario promises: `is_error` on the event and the `tool_result`, the ticker in the message, and the run still ending `"done"`.
    **Lesson:** copy a test's structure, then rewrite every assertion from the scenario's own contract.

## Check questions
??? question "In the step-limit test, suppose you script exactly 3 replies and someone changes `while steps < max_steps` to `<=`. What fails, and why is that worse than with 5 replies?"
    **My answer:** one extra step is done. Right, but only half of it.

    **Full answer:** the 4th request finds the script empty, and `FakeClaude.handler` raises `IndexError: pop from empty list`. The test fails, but with an error that points at the fake, not the loop. With 5 replies the 4th call succeeds, and the failure is `assert 4 == 3` on the request count, which names the bug directly.

??? question "The buggy-tool test expects a `RuntimeError`, but the tool-error test expects none. Why the difference, and where does the `RuntimeError` end up behind `POST /chat`?"
    **My answer:** a ToolError is captured while a RuntimeError is not. That's what happens, not why or where.

    **Full answer:** a `ToolError` is an expected failure the model can act on ("no such ticker"), so it becomes an error `tool_result` and the loop carries on. A `RuntimeError` is a bug, and turning it into a message would hide it. It propagates out of `stream_agent`, and `_stream` in `api/chat.py` catches it, rolls back the whole run, logs it and sends an `error` event.

## Guided exercise
**Task (break something on purpose):** plant three bugs in `agent/loop.py`, one at a time, and predict which tests fail before running `uv run pytest tests/test_loop.py -q`. (a) Each tool result in its own user message. (b) `<=` in the step check. (c) `ToolError` removed from `_run_tool`'s `except`. Then find one line you can break without any test failing. Undo each bug; `git diff src/` must be empty.

**Outcome:** done (predictions mine, runs by Claude, `git diff src/` empty after each one):

| Bug | My prediction | What happened |
|---|---|---|
| (a) one user message per tool result | the loop fails, because Claude expects every result in the next call | Only the parallel-calls test failed: `['toolu_b'] == ['toolu_a', 'toolu_b']`. The fake doesn't enforce the API's rules; our assertion caught it |
| (b) `<=` in the step check | an extra step, so the step-limit test fails | As predicted: `assert 4 == 3` on `steps` |
| (c) `ToolError` not caught in `_run_tool` | "silently" treated as a bare exception | Right test, but loud: the `ToolError` escaped and crashed the test |
| (d1) `system=SYSTEM_PROMPT` deleted | (found with Claude) | **Survived**: all 15 passed |
| (d2) `duration_ms` in seconds instead of ms | (found with Claude) | **Survived**: all 15 passed |

Closed (d1): the worked example now checks that every request carries `MODEL`, `SYSTEM_PROMPT` and all tool names, and the mutant fails it. Left (d2) open on purpose: telling ms from seconds would need a timing assertion, which makes a test flaky.

**What I got wrong:** (a) I expected the fake (as if it were the API) to reject separate messages; it accepts anything. (c) "silently": an uncaught exception is the loudest outcome. (d) I didn't spot a surviving line myself.

**Lesson:** a fake checks only what the tests assert, nothing more. Lines that run in every test can still be wrong without any test noticing. Coverage says a line ran; a planted bug shows whether a test notices.

## Explain it in 2 minutes
The agent loop talks to Claude, so testing it seems to need Claude. It doesn't. The real SDK client gets an HTTP transport that answers from a script, so every test decides exactly what Claude "says" and runs the same way every time, for free. The tests then check the loop's contract: the events it yields, the result it returns, the requests it sends back to Claude (read from the actual HTTP bodies), and what's in the database. That covers a tool call followed by an answer, a tool error that goes back to Claude as data, an unknown tool, two parallel calls whose results go back in one message, the step limit, writes that wait for a human, and a buggy tool whose exception propagates while its savepoint undoes its writes. To check the tests themselves, I planted bugs on purpose and checked that a test failed for each one. That's mutation testing by hand.
