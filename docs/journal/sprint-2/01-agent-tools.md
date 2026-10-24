---
tags:
  - agents
  - errors
---

# 1. Agent tools

**Sprint 2** · **Date:** 2026-10-24 · **Plan item:** `tools/`: typed tool functions: `get_company_facts` (Cala), `search_filings` (EDGAR for now; retrieval in S3), `list_watchlist`, `add_to_watchlist`, `remove_from_watchlist`

## What and why
The five functions the agent can call, each with the definition the model reads (name, description, input schema). The model never runs code: it asks for a tool by name with arguments it generated, and our code validates and runs it. The package is protocol-neutral so the hand-written loop (task 3), LangGraph (task 7) and the MCP server (task 9) can all wrap the same tools.

## Decisions
| Date | Decision | Why | Alternatives considered | ADR |
|---|---|---|---|---|
| 2026-10-24 | One `Tool` object per tool: name, description, Pydantic input model, async handler, `writes` flag | One place per tool; the schema is generated from the input model so it can't drift from the code, and Pydantic validates the model's arguments before anything runs | The SDK's `@beta_tool` and tool runner (runs the loop for us, and the loop is what I'm meant to write); hand-written JSON schemas (two sources of truth); MCP tools from the start (ties the tools to one protocol) | — |
| 2026-10-24 | Dependencies (DB session, Cala, EDGAR) arrive in a `ToolContext` | Same dependency injection as Sprint 1: tests pass `MockTransport` clients and the test database | Globals or building clients inside each tool (untestable offline) | — |
| 2026-10-24 | Tools return small Pydantic models as JSON, `None` fields dropped; `get_company_facts` flattens Cala's `{value, sources}` per property into `facts` plus one `sources` list | Every byte returned is input tokens on the next turn | Return the raw API payload (repeats sources on every property, costs more, says nothing more) | — |
| 2026-10-24 | Tools raise; they don't build error `tool_result`s. `ToolError` marks messages written for the model; other exceptions propagate | Turning exceptions into `tool_result`s is the loop's job (task 3); separating "for the model" from "our problem" keeps bugs visible and internals out of answers | Catch everything and return `str(exc)` (hides bugs, leaks URLs and response bodies) | — |
| 2026-10-24 | An unknown ticker becomes `UnknownTickerError` in `watchlist.py`, around `get_company` only | Only that call means "unknown ticker"; a 404 from `list_filings` is also an `EdgarNotFoundError` but the ticker exists | Catch `EdgarNotFoundError` in the tool (can't tell which call failed) | — |
| 2026-10-24 | `search_filings` returns filing metadata and links only, and its description says so | Filing text needs retrieval (Sprint 3); saying so stops the model from inventing what a 10-K says | Fetch and truncate the whole document (huge, and the wrong slice) | — |

## Concepts

### Tool definitions are part of the prompt
With tool use the model never runs code. Each request carries a list of tools: `name`, `description` and `input_schema` (JSON Schema). When the model wants one it replies with a `tool_use` block (a name plus arguments it generated); we run the function and send back a `tool_result`. The model chooses tools only from what those three fields say, so a description is prompt engineering: say what the tool returns, **when to use it and when not to**, and its limits. Here `get_company_facts` says "not for strategy or risks, use `search_filings`", and `search_filings` says "returns no filing text yet; say so rather than guess".

### JSON Schema from Pydantic
`InputModel.model_json_schema()` turns a Pydantic model into the JSON Schema the API wants. Types, defaults and constraints carry over: `Literal["10-K", "10-Q", "8-K"]` becomes an `enum` the model can see, `Field(ge=1, le=20)` becomes `minimum`/`maximum`, `Field(description=...)` documents each argument. The same model then validates what the model sent (`model_validate`), so one class is the contract **and** the guard. Bad arguments (`limit: 50`) raise a `ValidationError` before the handler runs: no API call, no DB write.

### The tool registry
`TOOLS: dict[str, Tool]` in `tools/__init__.py` maps a tool's name to its object. The model answers with a name; the loop does `TOOLS[name].run(ctx, arguments)`. Sending definitions is `[t.definition() for t in TOOLS.values()]`. A name that isn't in the dict is a model mistake the loop has to handle (task 3).

### Read tools and write tools
A read tool (facts, filings, list the watchlist) can run as often as the model likes. A write tool (add or remove from the watchlist) changes state for the user, so it should only run when the user asked and, in task 4, after a human approves it. The `writes=True` flag on the `Tool` is what the loop will check. Marking it now, in the definition, means the safety rule lives next to the tool and can't be forgotten in one caller.

### Tool output size is a token cost
A `tool_result` is appended to the conversation and sent back on every later turn of that run. A 5 KB raw API payload in step 1 is paid again in steps 2, 3, 4… So tools return only what helps the answer: `model_dump_json(exclude_none=True)`, flattened properties, one deduplicated list of sources.

### Exception propagation
When an exception is raised, Python unwinds the call stack one frame at a time. At each frame it checks: is this line inside a `try` with a matching `except`? If not, it leaves the function and asks the frame above. "Propagates" means nobody caught it. Here a 404 from `edgar.list_filings` passes through `watchlist.add_to_watchlist` (its `try` only wraps `get_company`), through the tool (it only catches two domain errors), through `Tool.run`, and reaches the caller: a test today, the loop in task 3.

### Translate errors where their meaning is known
Each layer speaks its own language. A client error says what HTTP did (`EdgarNotFoundError`: some URL returned 404). A domain error says what happened in the business (`UnknownTickerError`). A `ToolError` says what the model should do next ("check the ticker or look it up with `get_company_facts`"). Translate at the **lowest layer that still knows what the error means**: the EDGAR client doesn't know a watchlist exists; the tool can't tell which of two EDGAR calls failed; `watchlist.add_to_watchlist`, right around `get_company`, knows both.

### Exception chaining with `from`
`raise ToolError("...") from exc` stores the original exception on `__cause__`. `str()` of the new exception is only its own message, so what the model sees (the loop will send `str(exc)`) stays clean, while a traceback in the logs shows both: the original error, then "The above exception was the direct cause of the following exception". Without `from`, the traceback says "During handling of the above exception, another exception occurred", which reads like a crash in the `except`; `from None` drops the cause and loses the real reason when debugging.

## Code map
| File | What it does | Why it exists / why this way |
|---|---|---|
| `backend/src/market_desk/tools/base.py` | `Tool` (definition + `run`), `ToolContext`, `ToolError` | One shape for every tool; `run` validates, executes and serialises so callers don't repeat it |
| `backend/src/market_desk/tools/companies.py` | `get_company_facts`: Cala search (5 candidates) → first `Company` → entity details, flattened | Name search is loose ("Apple" also finds Apple Records); flattening saves tokens |
| `backend/src/market_desk/tools/filings.py` | `search_filings`: EDGAR company → filings with archive URLs | Metadata and links only until Sprint 3's retrieval; unknown ticker → `ToolError` |
| `backend/src/market_desk/tools/watchlist.py` | `list_watchlist`, `add_to_watchlist`, `remove_from_watchlist` | Thin wrappers: the logic stays in `market_desk/watchlist.py`; add and remove are `writes=True` |
| `backend/src/market_desk/tools/__init__.py` | The `TOOLS` registry | The loop looks tools up by the name the model sends |
| `backend/src/market_desk/watchlist.py` | New `UnknownTickerError`, raised around `get_company` only | Only that call means "unknown ticker" |
| `backend/tests/test_tools.py` | Definitions, schema, write flags, bad arguments, each tool on fakes, error paths | Routed fake Cala + the existing fake SEC + the test database: no live calls |
| `backend/tests/test_watchlist.py` | Unknown ticker raises and adds nothing | The domain error is tested where it's raised |

## Gotchas
!!! bug "(exercise) `test_adding_twice_is_a_tool_error` went red after adding unknown-ticker handling"
    **Cause:** one `except (EdgarNotFoundError, AlreadyWatchedError)` with one generic message ("Error adding ticker X to the watchlist") replaced the specific "already on the watchlist".
    **Fix:** one `except` per error, each with its own message.
    **Lesson:** the two failures need different reactions from the model (tell the user it's already there vs check the ticker). A generic message leaves the model guessing.

!!! bug "(exercise) An unknown-ticker message that could be false"
    **Cause:** the tool caught `EdgarNotFoundError` around all of `watchlist.add_to_watchlist`, which calls EDGAR twice. A 404 on `list_filings` (the ticker exists) would also be reported as "ticker not found"; and a catch for `EdgarResponseError` could fire from `get_company` too, despite saying "could not list filings".
    **Fix:** `UnknownTickerError` raised in `watchlist.py` around `get_company` only; the tool catches domain errors; other `EdgarError`s propagate to the loop.
    **Lesson:** an exception's type doesn't tell you which call raised it. Translate where the meaning is still known.

!!! bug "(found, open) A failed add can leave a pending watchlist entry in the session"
    **Cause:** `add_to_watchlist` calls `session.add(entry)` before `list_filings`. If that call raises, the exception escapes before `commit()`, and the entry stays pending in the session.
    **Fix:** not yet. Whoever owns the session must `rollback()` when a tool fails; decide in task 3.
    **Lesson:** an exception that propagates skips the code after it, including the commit, but doesn't undo what was already added to the session.

!!! bug "`ruff format` dedented the example in a docstring"
    **Cause:** ruff formats code it finds in docstrings; an indented example block at the top of `tools/__init__.py` was reformatted.
    **Fix:** accepted the formatter's output.
    **Lesson:** `make check` runs `ruff format --check`; when it fails on code you didn't touch logically, run `ruff format` and look at the diff.

## Check questions
??? question "The model calls `search_filings` with `{\"ticker\": \"AAPL\", \"limit\": 50}`. What happens, where, and does EDGAR get called?"
    `Tool.run` calls `SearchFilingsInput.model_validate(arguments)` first; `limit` has `le=20`, so it raises `ValidationError`. The handler never runs, so EDGAR isn't called. The loop will send the validation error back and the model can retry with 20.

??? question "What's the risk of the loop catching every exception and sending `str(exc)` back to the model?"
    Tokens are a small cost. The bigger risks: it hides our own bugs (a `KeyError` in our code becomes text the model works around), it leaks internals (URLs, SQL, response bodies) that can end up in the answer, and raw messages ("404 for https://…") don't tell the model what to do next. `ToolError` marks the messages meant for the model; the rest gets logged and a generic error goes back.

## Guided exercise
**Task (extend a feature, test first):** turn an unknown ticker in `search_filings` and `add_to_watchlist` into a `ToolError` whose message contains the ticker and tells the model what to do next; tests expect `ToolError` with the ticker; `make check` green.

**Outcome:** done. `search_filings` wraps only `get_company` and raises a `ToolError` with an upper-cased ticker and a hint; tests use `match="ZZZZ"`. For `add_to_watchlist`, Claude moved the translation into `watchlist.py` (`UnknownTickerError`) on request.

**What I got wrong:** first one generic message for two different errors (broke the "already watched" test); then catching `EdgarNotFoundError` and `EdgarResponseError` around a function that calls EDGAR twice, so the message could be false. Also: unused import, unsorted imports, a line over 100 characters.

**Lesson:** each failure the model can act on gets its own message; translate an error where you still know which call raised it; errors the model can't fix propagate.

## Explain it in 2 minutes
An agent's tools are two things: a contract the model reads and a function we run. The contract is a name, a description and a JSON Schema; I generate the schema from a Pydantic model, so the same class documents the arguments and validates what the model sends. The description is prompt engineering: it says when to use the tool and what it can't do, which is how the model learns that Cala is for facts and filings are for what a company says. Each tool returns a small JSON result, because whatever it returns is paid for in tokens on every later turn. Write tools are flagged so the API can ask a human first. For errors, I separate messages meant for the model, like "unknown ticker, check it", from failures that are our problem, like a malformed SEC response: the first become a `ToolError`, translated at the layer that knows what went wrong; the second propagate to the loop, which logs them and tells the model something generic.
