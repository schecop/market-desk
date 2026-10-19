---
tags:
  - http
  - integrations
---

# 2. Cala client

**Sprint 1** · **Date:** 2026-10-16 · **Plan item:** `clients/cala.py`: typed client (auth header, timeouts, retries with backoff on 429/5xx, `Retry-After`, pagination, custom exceptions); **write it yourself**

## What and why
A small typed "SDK" for Cala: auth, timeouts, retries and error mapping in one place, returning Pydantic models. The agent (Sprint 2) calls methods like `search_entities()` and never sees HTTP or raw JSON.

## Decisions
| Date | Decision | Why | Alternatives considered | ADR |
|---|---|---|---|---|
| 2026-10-16 | `httpx2` instead of `httpx` | Maintained successor, same API; `httpx` has had no release since Dec 2024 | `httpx` 0.28 | [ADR-0003](../../adr/0003-http-client-design.md) |
| 2026-10-16 | Async (`AsyncClient`) | FastAPI is async; parallel tool calls; voice in Sprint 5 | Sync client (rewrite later) | [ADR-0003](../../adr/0003-http-client-design.md) |
| 2026-10-16 | Retries with tenacity | The standard library for it; declarative and more maintainable than a hand-written loop | Hand-written retry loop | [ADR-0003](../../adr/0003-http-client-design.md) |
| 2026-10-16 | Tests through an injected `httpx2.MockTransport` | respx only patches `httpx`; injection needs no global patching | respx | [ADR-0003](../../adr/0003-http-client-design.md) |
| 2026-10-16 | Wrap `search_entities`, `search` and (as the exercise) `get_entity`; `query` and `introspection` later, with the same pattern | What the agent needs first; every call costs quota | All five endpoints at once | |
| 2026-10-17 | The status code decides the exception; the body only adds detail | A 429 with an HTML body must stay retryable; a 422 must never be retried, whatever its body | Map by body shape (breaks on Cala's two error shapes and on proxy HTML) | |
| 2026-10-17 | A 200 whose body doesn't fit the model raises `CalaResponseError`, not `CalaValidationError` | `CalaValidationError` means "our request is wrong"; a bad 200 means Cala broke its contract. Mixing them makes logs and the agent blame the wrong side | One exception for every "invalid" thing | |
| 2026-10-18 | Retries with `AsyncRetrying` inside `_request`, not the `@retry` decorator | A decorator is evaluated once, when the class is defined, so it can't read `self._sleep`. `AsyncRetrying` is built per call, so the injected `sleep` works and tests need no global patching | `@retry` plus patching `_get.retry.sleep` or `asyncio.sleep` in tests; `_get.retry_with(...)` | |
| 2026-10-18 | Give up at once on a `429` whose `Retry-After` is over 30 s (`_should_retry`) | The agent prefers a fast error to hanging; each retry also costs one of the 100 calls | Cap the wait at 30 s and retry anyway; always obey the header | |
| 2026-10-18 | At most 3 attempts | Every retry spends Cala quota | 5 attempts (more resilient, more quota) | |
| 2026-10-18 | One `_request(method, path, *, params, json)` for every endpoint | Errors and retries live in one place; `search` and `get_entity` got them for free | A `_get` and a `_post` with duplicated retry logic | |
| 2026-10-18 | `search` sends `explainability: false` and models only `content`, `context`, `entities` | Tolerant reader: model what we use; smaller and faster responses. Revisit for tracing (Sprint 6) | Model the whole `Answer` schema | |
| 2026-10-19 | `get_entity` takes `direction: Literal["outgoing", "incoming"]`; the relationship name is a dict key, never a branch | Direction is relative to the entity asked about, so only the caller knows it; any relationship type must work | Hard-code direction per relationship name (my first version: only two names worked) | |
| 2026-10-19 | `relationships` defaults to empty (tolerant), and `outgoing`/`incoming` default to `{}`, not `None` | You only get relationships when you ask for them; `{}` gives "no relationships" one representation, so callers need no `None` check | Strict (no default: a missing key raises `CalaResponseError`, as the spec marks it required); `None` defaults | |
| 2026-10-16 | `httpx2` and `tenacity` are runtime dependencies (`httpx2` moved out of the dev group) | The client ships in the production image, not only in tests | | |

## Concepts
### Dependency injection (the transport)
The client doesn't decide where its responses come from: it receives a `transport` in its constructor and passes it to `httpx2.AsyncClient`. In production it's `None` (the real network); in tests it's an `httpx2.MockTransport(handler)`, a function that returns any response we want. No global patching, and every failure (429, 500, HTML, timeout) is reproducible offline. It only works if the dependency reaches the place that uses it: a `transport` parameter that's accepted but never passed on means the tests silently hit the real API.

### `classmethod` as an alternative constructor
`@classmethod def from_settings(cls, settings, timeout)` receives the class (`cls`), not an instance, and ends with `return cls(...)`. It separates "how to build from app config" (check the key, unwrap the `SecretStr`) from `__init__`, which takes plain values and stays easy to use in tests. Same idea as `dict.fromkeys()` or `datetime.fromtimestamp()`.

### Async context manager (`async with`)
`__aenter__` runs on entering the block and returns what `as client` receives. `__aexit__(exc_type, exc, tb)` runs on leaving, **also when the block raised**. Returning `None` lets the exception keep propagating. Here it calls `close()`, so the connection pool is released even after a 429. Order: `__aexit__` first, then the caller's `except`. `close()` stays public for lifecycles that don't fit a block (FastAPI startup and shutdown).

### Exceptions that carry data
An exception is an object: give it attributes (`retry_after: float | None`, `error_type`, `message`) instead of packing everything into the message string. Code reads the attributes (tenacity will wait `retry_after` seconds); humans read `str(exc)`. Keep them separate: `self.message` holds Cala's clean text, and `super().__init__(f"{error_type}: {message}")` builds the log line.

### Exception chaining (`raise ... from err`)
Inside an `except`, `raise CalaResponseError(...) from err` records the original error as the cause. The traceback then shows both ("The above exception was the direct cause of..."), so you still see *which* field failed validation. Ruff's rule B904 enforces it.

### Status code first, body second
For error mapping, the status code is the reliable signal and the body is optional detail: it can be the documented shape, another shape, or HTML from a proxy. So each branch picks the exception from the status, then tries to read the body defensively (`_json_dict` returns `{}` if it isn't a JSON object). A 429 in HTML is still a `CalaRateLimitError`, and stays retryable.

### Generic functions (`def f[M: BaseModel]`)
Python 3.12 syntax for a type variable: `_parse[M: BaseModel](response, model: type[M]) -> M` means "give me a model class, get back an instance of *that* class". mypy then knows `self._parse(response, EntitySearchResponse).entities` is `list[Entity]`. Older spelling: `M = TypeVar("M", bound=BaseModel)`.


### Retrying with tenacity
Four pieces: `retry=` decides **whether** (here `retry_if_exception(_should_retry)`: rate limits, 5xx, network errors), `stop=` **how many times** (`stop_after_attempt(MAX_ATTEMPTS)`), `wait=` **how long** (a custom `_wait`: `retry_after` if Cala sent it, else `wait_exponential_jitter`), and `reraise=True` so the caller gets our `CalaError`, not a `tenacity.RetryError`. `before_sleep=` runs before each wait: that's where the retry is logged. In async code:
```python
async for attempt in AsyncRetrying(retry=..., stop=..., wait=..., sleep=self._sleep, reraise=True):
    with attempt:
        ...              # raise → tenacity decides; return → done
```
**Jitter** adds randomness to the backoff, so many clients that failed together don't all retry at the same instant.

### Decorator vs object configuration
A decorator (`@retry(...)`) is evaluated once, when the class is defined, before any instance exists, so its configuration can't depend on `self`. Building `AsyncRetrying(...)` inside the method happens per call, when `self._sleep` exists. Rule of thumb: the decorator for fixed policies; the object form when the policy depends on the instance or you retry only part of a method.

### Idempotency
An operation is **idempotent** if doing it twice has the same effect as doing it once. `GET` is idempotent by definition; `POST` may not be (creating an order twice). Only idempotent operations are safe to retry blindly. Cala's `POST /v1/knowledge/search` is a read that uses `POST` to carry a body, so it is retried like a `GET`. APIs that create things accept an `Idempotency-Key` header: on a repeat, the server returns the stored result instead of acting again.

### Directed relationships in a knowledge graph
Cala stores facts as arrows from a subject to an object: `Apple ─IS_REGISTERED_IN→ United States`. **Outgoing** relationships start at the entity you ask about; **incoming** ones point at it. The same type flips with the point of view: for Apple, `IS_BOARD_MEMBER_OF` is incoming ("who sits on Apple's board"); for Tim Cook, it's outgoing ("which boards he sits on"). So direction is a parameter of the question, and `GET /v1/entities/{id}/introspection` lists which relationship types an entity has.

### `Literal` types
`direction: Literal["outgoing", "incoming"]` accepts only those two strings: mypy rejects `"outgoin"` before the code runs, and the signature documents the options. Lighter than an `Enum` when the values are just strings sent to an API.

### `Field(default_factory=...)`
`Field(default_factory=dict)` builds a **new** default for every instance. In plain Python a mutable default (`def f(x=[])`) is created once and shared between calls, a classic bug. Pydantic copies plain defaults anyway, but `default_factory` states the intent and is the habit that's correct everywhere.

### Model order and forward references
Pydantic evaluates field types when each class is created, top to bottom, so a model must come after the models it uses (`Source`, `Document` → `Origin` → `KnowBit` → `SearchAnswer`). Otherwise: `NameError` on import. mypy doesn't notice, because it reads the whole file first: here the tests caught what types missed.

## Code map
| File | What it does | Why it exists / why this way |
|---|---|---|
| `backend/src/market_desk/clients/cala.py` | `CalaClient` (`from_settings`, `async with`, `search_entities`, `search`, `get_entity`), Pydantic models, the `CalaError` hierarchy, `_request` (retries), `_raise_for_error`, `_parse`; the retry policy (`MAX_ATTEMPTS`, `MAX_RETRY_AFTER`, `_wait`, `_should_retry`, `_log_retry`) | One place for auth, timeouts, errors and retries; the agent only sees models and `CalaError`s |
| `backend/tests/test_cala_client.py` | Step 1: the request sent (method, path, params, header), typed results, `async with` closes, `from_settings` | Proves the transport is used and the key comes from settings |
| `backend/tests/test_cala_errors.py` | Step 2: one test per error case (422, 429, 5xx, other 4xx, bad 200), including HTML bodies and a non-numeric `Retry-After` | Locks in "status decides, body adds detail" |
| `backend/tests/test_cala_retries.py` | Step 3: recovers (429→200 honouring `Retry-After`, timeout→200, backoff), gives up (3×500, 3 timeouts), never retries a 422, fails fast on a long `Retry-After`, logs each retry | `scripted_transport` plays a sequence of responses; `FakeSleep` records waits without waiting |
| `backend/tests/test_cala_search.py` | Step 4: `POST` with the JSON body, typed answer with sources, `entities: null`, a retried 429 | The idempotent POST gets the same retry policy |
| `backend/tests/test_cala_entity.py` | Exercise: empty body without a relationship, `limit`/`offset` under the direction, any relationship type, tolerant parsing | Relationship paging, the only pagination Cala has |
| `backend/src/market_desk/clients/__init__.py` | Marks `clients/` as a package | Home for Cala and EDGAR clients |
| `backend/pyproject.toml`, `uv.lock` | `httpx2` and `tenacity` in `dependencies` | Needed at runtime |

## Gotchas
!!! bug "`staticmethod` used with a non-method, and the client lost two methods"
    **Symptom:** mypy reported `"staticmethod" used with a non-method`; `_parse` and `_raise_for_error` stopped existing on the client.
    **Cause:** `_wait` was pasted at column 0 in the middle of the class. That ended the class there, and the indented methods below became dead code nested inside `_wait`.
    **Fix:** module-level helpers go after the class, with the other `_` functions.
    **Lesson:** in Python, indentation *is* structure. Moving a block changes what it belongs to.

!!! bug "`object list can't be used in 'await' expression`, deep inside httpx2"
    **Symptom:** the traceback ended in `httpx2/_transports/mock.py`, not in my code.
    **Cause:** I passed a list (`[Response(...)]`) to a helper that takes one response. The mock handler returned the list, and `MockTransport`, which also accepts async handlers, tried to `await` it.
    **Fix:** pass the response itself. mypy would have said it plainly: `incompatible type "list[Response]"; expected "Response"`.
    **Lesson:** when a traceback ends inside a library, look for the last thing my code handed it. Run mypy when something fails strangely.

!!! bug "Only two relationship types worked"
    **Symptom:** `get_entity(id, relationship="HAS_SUBSIDIARY")` sent no paging at all.
    **Cause:** the body was built with `if relationship == "IS_BOARD_MEMBER_OF" ... elif == "IS_REGISTERED_IN"`, copied from the spec's examples, with the direction hard-coded per name.
    **Fix:** the name and the direction are both data: `{direction: {relationship: {"limit": ..., "offset": ...}}}`.
    **Lesson:** an example in the docs isn't the full list. When values come from the caller, don't branch on them.

!!! bug "The `transport` parameter was accepted but never used"
    **Symptom:** (code review, before any test) `__init__` took `transport=` but built `httpx2.AsyncClient` without it.
    **Cause:** the parameter stopped at the constructor and never reached the object that makes requests.
    **Fix:** pass `transport=transport` to `AsyncClient`. The test that records requests in `seen` fails if it's ever dropped again.
    **Lesson:** with dependency injection, test that the fake is *actually used*. Otherwise "tests pass" can mean "tests called the real API".

!!! bug "Tests changed to match the code instead of the requirement"
    **Symptom:** tests named `..._raises_response_error` asserted `CalaValidationError`, and passed.
    **Cause:** the code raised `CalaValidationError` for a bad 200, and the tests were adjusted until green.
    **Fix:** the tests went back to `CalaResponseError` (the requirement), and the code was fixed.
    **Lesson:** a test states what you *want*. If the test and the code disagree, decide which one is wrong before editing either.

!!! bug "My own skeleton test contradicted the rule"
    **Symptom:** the skeleton expected a 422 with an HTML body to raise `CalaResponseError`, and a 429 with HTML did the same in the code. That 429 would never have been retried.
    **Cause:** classifying by "can the body be read?" instead of by status code.
    **Fix:** a 422 stays `CalaValidationError` and a 429 stays `CalaRateLimitError` whatever the body; tests added for both.
    **Lesson:** the status code decides the exception. Even a reviewer's tests need reviewing.


## Check questions
??? question "Cala answers `429` with `Retry-After: 2` and an HTML body. Which exception, and what `retry_after`? And with `-5`?"
    `CalaRateLimitError` with `retry_after == 2.0` (a float): the status decides, so an HTML body doesn't change the type. With `-5`, `retry_after` is `None` ("unknown"): a negative wait makes no sense.

??? question "Cala adds a new field to every entity (`\"country\": \"US\"`). Does `_parse` fail?"
    No. Pydantic's default is `extra="ignore"`: unknown fields are dropped silently. It could be changed in `model_config` (`extra="forbid"`), but for an external API that would break the client whenever the provider adds a field. This is the **tolerant reader** principle: validate what you use, ignore the rest.

??? question "If the POST created an order (`POST /v1/orders`) and the first attempt timed out, why is retrying dangerous? What makes it safe?"
    The operation isn't **idempotent**: the first request may have reached the server before the timeout, so a retry could create a second order. Serious APIs accept an `Idempotency-Key` header (a UUID the client generates per operation). The server stores the result for that key and, on a repeat, **returns the same response** instead of acting again. It doesn't reject the repeat: the client still gets its answer. Cala's `/v1/knowledge/search` is a read that uses `POST` only to carry a body, so it's idempotent and safe to retry.

??? question "Cala answers 500, then 429 with `Retry-After: 45`. How many requests, how many sleeps, what reaches the caller?"
    2 requests, 1 sleep, `CalaRateLimitError`. Attempt 1 (500) is retried after one backoff sleep. Attempt 2 (429, 45 s) is above the 30 s limit, so `_should_retry` returns `False` and the error is raised at once: no second sleep, and the third attempt is never spent. (My first answer got the counts right but said the 429 was retried "because it's under 30": it's over.)

## Guided exercise
**Task (extend with a small feature):** add `get_entity(entity_id, relationship=None, *, direction, limit, offset) -> EntityDetails` for `POST /v1/entities/{entity_id}`, the only pagination Cala has (per relationship type). Acceptance: an empty body without a relationship; `limit`/`offset` under the right direction; any relationship type; tolerant parsing of a missing or empty `relationships`; `make check` green.

**Outcome:** done: 6 tests in `test_cala_entity.py`, 43 in total. Claude wrote the test skeleton and, on request, the near-solution with a `TODO` for the body keys, which I completed.

**What I got wrong:** the first version branched on two relationship names from the spec's example and hard-coded their direction, so any other type was silently dropped. I edited the first test's expected body to match the code (`{"relationships": {}}`) instead of the criterion (`{}`). I passed a list to a single-response helper, and the error surfaced deep in httpx2. I asked why a spec-required field should get a default: the answer is a trade-off (strict vs tolerant), not a rule.

**Lesson:** values from the caller are data, not branches. A test states the requirement: change it only when the requirement changes, as with `None` → `{}` for empty relationships.

## Explain it in 2 minutes
The Cala client is a small typed SDK: the agent calls `search_entities`, `search` or `get_entity` and gets Pydantic models back, or a `CalaError` subclass; it never sees HTTP or raw JSON. Every call goes through one `_request` method that owns auth, timeouts, error mapping and retries. Errors are mapped by **status code first**: a 422 means our request is wrong and is never retried; 429, 5xx and network failures are temporary and are retried with tenacity, up to 3 attempts, because every call spends Cala quota. The wait uses Cala's `Retry-After` when it sends one, or exponential backoff with jitter; a `Retry-After` over 30 seconds fails fast rather than blocking the agent. Each retry is logged. A success whose body doesn't fit the model is a different error: Cala broke its contract. To debug a failing integration I'd read the retry logs, then reproduce the exact responses offline: the client takes its transport in the constructor, so a test can replay any sequence (a 429 then a 200, three timeouts, an HTML error page) without spending a single real call. The same trick with `sleep` makes retry tests instant.
