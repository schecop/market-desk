---
tags:
  - http
  - integrations
---

# 3. EDGAR client

**Sprint 1** · **Date:** 2026-10-19 · **Plan item:** `clients/edgar.py`: company lookup (ticker → CIK), filings list, filing document fetch; required User-Agent; client-side rate limiting; local response cache for development

## What and why
A typed async client for SEC EDGAR, the second data source: map a ticker to its CIK, list a company's filings (10-K, 10-Q...) and download a filing's document. It feeds the RAG pipeline in Sprint 3.

## Decisions
| Date | Decision | Why | Alternatives considered | ADR |
|---|---|---|---|---|
| 2026-10-19 | One `AsyncClient` for both hosts (`www.sec.gov`, `data.sec.gov`), absolute URLs | The 10 requests/second limit is per user, not per host: one client, one limiter | Two clients (two limiters, double the real rate) | |
| 2026-10-19 | Rate limit with `aiolimiter` (10/s), injected | Stay under the SEC's limit proactively; a maintained library instead of a hand-written limiter | Hand-written limiter | [ADR-0004](../../adr/0004-edgar-rate-limit-and-dev-cache.md) |
| 2026-10-19 | Dev-only cache with `hishel` (`FilterPolicy`, SQLite), enabled by `EDGAR_CACHE_DIR` | Filings never change; the SEC's `Cache-Control` (`max-age=6` or none) would defeat RFC caching | Hand-written disk cache; RFC `SpecificationPolicy` | [ADR-0004](../../adr/0004-edgar-rate-limit-and-dev-cache.md) |
| 2026-10-19 | Same error and retry pattern as Cala; no shared base class yet | Rule of three: with two clients it's not yet clear what's really common | Extract a base `HttpClient` now | |
| 2026-10-20 | The cache stores only 200s (`_OnlySuccess` response filter) | Measured: `FilterPolicy` with no filters cached 500, 404 and 403 too, so one SEC hiccup would be replayed until the cache is deleted | No filter; cache errors with a short TTL | [ADR-0004](../../adr/0004-edgar-rate-limit-and-dev-cache.md) |
| 2026-10-20 | `dev_cache_transport(cache_dir, next_transport=None)` is a module-level function that `from_settings` calls | Tests put a `MockTransport` behind the cache and count what reaches the "network"; the client itself doesn't know a cache exists | Build the cache inside `__init__` (untestable without the real network) | |
| 2026-10-20 | `get_cik` keeps a `dict[str, int]` (ticker → CIK), built once from the tickers file | One download; every lookup is a dict access, case-insensitive, and typed as `int` | Keep the raw file and loop over 10,443 entries per lookup | |
| 2026-10-20 | Removed code copied from the Cala client that EDGAR doesn't need (`_parse`, the 422 branch, `EdgarValidationError`, `params`/`json` in `_request`) | Copy the pattern, not the semantics: EDGAR has no 422 shape and only does `GET`s with full URLs; dead code misleads the next reader | Keep it "for symmetry" | |
| 2026-10-21 | Keep our client for fetching; don't adopt `edgartools` now | Ours is finished, async, offline-testable through transport injection, and consistent with the Cala client. `edgartools` brings pandas/pyarrow, the old `httpx`, a sync API with global identity and its own retry policy | `edgartools` for everything; revisit its *parsing* in Sprint 3 | [ADR-0004](../../adr/0004-edgar-rate-limit-and-dev-cache.md) |
| 2026-10-19 | Test fixtures from real responses, trimmed (4 tickers, 17 filing rows, the first 3 KB of a 10-K) | Tests use the real shape of the data; EDGAR is free, so 4 live calls are affordable | Hand-written fixtures (can drift from reality); full responses (MBs in the repo) | |

## What EDGAR looks like
Measured on 2026-10-19 with real calls:

| Resource | URL | Shape | Size |
|---|---|---|---|
| Ticker → CIK | `https://www.sec.gov/files/company_tickers.json` | A dict keyed by **position**, not by ticker: `{"0": {"cik_str": 1045810, "ticker": "NVDA", "title": "NVIDIA CORP"}, ...}`; `cik_str` is an **int** despite its name | ~800 KB, 10,443 companies; `Cache-Control: max-age=6` |
| A company's filings | `https://data.sec.gov/submissions/CIK0000320193.json` | Company facts plus `filings.recent`: **parallel columns** (`form[]`, `filingDate[]`, `accessionNumber[]`, `primaryDocument[]`...), up to 1,000 rows; older filings in extra pages under `filings.files` | ~160 KB for Apple; no `Cache-Control` |
| A document | `https://www.sec.gov/Archives/edgar/data/{cik}/{accession without dashes}/{primaryDocument}` | HTML (inline XBRL for 10-K and 10-Q) | Apple's FY2025 10-K: ~1.5 MB |

- **CIK formats differ:** an int in the tickers file, a zero-padded 10-digit string (`"0000320193"`) in submissions and its URL, unpadded in Archives URLs.
- **Rules:** at most 10 requests per second; a `User-Agent` with a name and a contact email on every request.

## Concepts
### Client-side rate limiting
Two ways to respect a provider's limit. **Reactive:** send freely and back off when the server says `429` (Cala). **Proactive:** never exceed the limit in the first place, by waiting before each request when needed (EDGAR, which blocks offenders). A *leaky bucket* lets requests through at a steady rate (10 per second) and makes extra ones wait their turn.

### Caching as a transport layer
`hishel.httpx2.AsyncCacheTransport(next_transport=...)` wraps another transport: on a request it looks in its storage first and only calls `next_transport` on a miss. The client above it doesn't change at all; it's the same dependency injection as `MockTransport`, stacked: `client → cache → network`. In tests, `next_transport` is a `MockTransport` that counts what gets through, so "the second request never reached the network" is a plain assertion.

### HTTP caching rules vs your own rules
HTTP caching (RFC 9111) lets the **server** decide: `Cache-Control: max-age=6` means "fresh for 6 seconds", and no header usually means "don't assume anything". Measured with hishel: under those rules the SEC's responses were never reused. A `FilterPolicy` lets the **client** decide instead: here, "keep every 200". That's only safe because we know the data: filings never change once published; a submissions list can go stale, which is acceptable in development.

### Parametrized tests
`@pytest.mark.parametrize("body", [...], ids=[...])` runs one test body once per input, and each run shows up separately (`test_unexpected_submissions_shape_raises_response_error[uneven-columns]`). One test covers three broken shapes, and a failure names the one that broke.

### `tmp_path`
A pytest fixture: a fresh, empty temporary directory per test, deleted by pytest later. The cache tests write their SQLite file there, so they never touch the real `.cache/` and never see each other's data.

## Code map
| File | What it does | Why it exists / why this way |
|---|---|---|
| `backend/src/market_desk/config.py` | `edgar_user_agent` and `edgar_cache_dir` (both optional; empty means unset) | Same pattern as `cala_api_key` |
| `.env.example`, `.gitignore` | `EDGAR_CACHE_DIR=.cache/edgar`; `.cache/` ignored at any depth | The dev cache never reaches Git |
| `backend/pyproject.toml`, `uv.lock` | `aiolimiter`, `hishel[httpx2]` | ADR-0004 |
| `backend/src/market_desk/clients/edgar.py` | `EdgarClient` (`from_settings`, `get_cik`, `list_filings`, `fetch_document`), `Filing`, the `EdgarError` hierarchy, `_request` (limiter + tenacity), `_raise_for_error` (403, 404, 429, 5xx), `dev_cache_transport` and its `_OnlySuccess` filter | One place for the SEC's rules: User-Agent, 10 req/s, retries, error mapping, the dev cache |
| `backend/tests/test_edgar_client.py` | 19 tests on the fixtures through a fake SEC that routes by URL (unknown URLs → 404): tickers, filings (columns → rows, form filter, limit, dates, `""` report dates), documents, User-Agent, 403/404/500, broken shapes (parametrized) | The real shape of the data, offline |
| `backend/tests/test_edgar_cache.py` | 4 tests: a repeat request is served from the cache, the cache survives a new client, errors aren't cached, `from_settings` creates the dir | Proves ADR-0004's cache behaves as decided |
| `backend/tests/fixtures/edgar/` | Trimmed real responses: tickers, Apple's submissions, the head of its FY2025 10-K | Tests run on the real shape of the data |

## Gotchas
!!! bug "`'FieldInfo' object has no attribute 'items'`"
    **Symptom:** `get_cik` crashed on its first call.
    **Cause:** the constructor had `company_tickers: dict = Field(default_factory=dict)`. `Field(...)` only means something inside a Pydantic model; in a plain function it's just an object used as the default. A `FieldInfo` is truthy, so `if not self.company_tickers` skipped the download, then `.items()` failed.
    **Fix:** internal state isn't a constructor parameter: `self._ciks: dict[str, int] | None = None` in `__init__`.
    **Lesson:** `default_factory` is Pydantic's tool. In plain Python: create the value in `__init__`, or use `param: X | None = None` and build it inside.

!!! bug "Retrying forever: tenacity's default is `stop_never`"
    **Symptom:** (code review) `_request` had `retry=` and `wait=` but no `stop=`.
    **Cause:** without `stop`, tenacity never gives up. A permanent 500 would hang the caller and hammer the SEC.
    **Fix:** `stop=stop_after_attempt(MAX_ATTEMPTS)`; `test_server_errors_stop_after_three_attempts` guards it. Without the fix that test wouldn't fail, it would **hang**: `FakeSleep` returns at once and the fake SEC always answers 500.
    **Lesson:** every retry loop needs an exit. A test that hangs is worse than one that fails.

!!! bug "The cache stored errors"
    **Symptom:** (measured before wiring it in) with `FilterPolicy()` and no filters, a 500, 404 or 403 came back from the cache on the next request.
    **Cause:** a `FilterPolicy` with no filters keeps every response.
    **Fix:** a response filter that keeps only 200s (`_OnlySuccess`); `test_errors_are_not_cached` guards it.
    **Lesson:** a cache decides *what* to keep, not only *how long*. Test the failure path of a cache, not just the hit.

!!! bug "I found `edgartools` only after building the client"
    **Symptom:** after the EDGAR client was done, a mature MIT library for EDGAR (`edgartools`) turned up, and it hadn't been weighed when the client was designed.
    **Cause:** the plan said "write the client", and nobody searched for an existing EDGAR library first, unlike `aiolimiter` and `hishel`, which were compared against hand-written versions.
    **Fix:** evaluated it after the fact: keep our client for fetching (async, testable, consistent), and spike its parsing in Sprint 3. Recorded in ADR-0004.
    **Lesson:** before writing any integration, search for an existing library and put it in the options, even when building your own is the point of the exercise.

!!! bug "`UnicodeEncodeError: 'charmap' codec can't encode character '\u2192'`"
    **Symptom:** a scratch script crashed on `print("... → ...")`.
    **Cause:** the Windows console used the cp1252 encoding, which has no `→`.
    **Fix:** plain ASCII in console output (or `PYTHONIOENCODING=utf-8`).
    **Lesson:** source files are UTF-8, but the console they print to may not be.


## Check questions
??? question "The limiter sits inside the `async for attempt` loop. What changes if it wraps the whole loop instead?"
    Every attempt must count towards the SEC's 10 requests/second, so it belongs inside. Outside, one token would cover up to three HTTP requests: a few calls retrying at the same moment would exceed the limit without the client knowing, which is exactly what gets you blocked, and right when the SEC is already failing (the 5xx that caused the retries). An `aiolimiter` limiter isn't a lock, so holding it through the backoff wouldn't block other callers; it would just under-count.

??? question "With the dev cache on, Apple files a new 10-K tomorrow. What does `list_filings(320193)` return in development?"
    The old list: the submissions response is cached, so the new 10-K doesn't appear. Refresh by deleting the cache dir (`.cache/edgar`). Only development is affected (production runs without the cache), and ADR-0004 accepts it on purpose. If it matters later (Sprint 3 ingestion): a short TTL for submissions, and keep documents forever, since a published filing never changes.


## Guided exercise
**Task (write a missing test):** nothing checked that the rate limiter is actually used: deleting `async with self._limiter:` left every EDGAR test green while the client broke the SEC's 10 requests/second. Write a test that fails if the limiter is removed, and that proves each **retry** goes through it too.

**Outcome:** done. `CountingLimiter(AsyncLimiter)` counts entries in `__aenter__` and then calls `await super().__aenter__()`, so it's still a real limiter. Two tests: one request → entered once; an always-500 server → 3 requests and entered 3 times (one per attempt, not per call). Commenting out `async with self._limiter:` turned them red; restoring it turned them green.

**What I got wrong:** nothing in the exercise itself. Earlier in the task: `Field(default_factory=...)` in a plain constructor, no `stop=` on the retries, and error semantics copied from Cala (see Gotchas).

**Lesson:** a test proves something only if it can fail. Breaking the code on purpose (a small *mutation*) is how you check that a test guards what it claims to guard. Reuse the parent with `super()` instead of copying its behaviour, so a fake stays faithful when the library changes.

## Explain it in 2 minutes
The EDGAR client is the second data source: it maps a ticker to the SEC's company ID (CIK), lists a company's filings and downloads a filing's document. EDGAR is free and has no quota, but it has rules: every request must carry a User-Agent with a contact email, and you may send at most 10 requests per second, or you get blocked. Cala tells us to slow down with a 429; EDGAR expects us to stay under the limit ourselves, so the client goes through a shared `aiolimiter` before every attempt, retries included, and a test proves it by counting. The data has quirks I checked with real calls first: the tickers file is keyed by position, so the client re-keys it once into a ticker → CIK dict; the CIK has three formats; and filings come as parallel columns that the client zips into rows, failing loudly if the columns don't line up. Errors map by status: 404 is "not found", 403 is "the SEC blocked you" and is never retried, 5xx and timeouts are retried three times. Anything unexpected in a successful body becomes one `EdgarResponseError`. For development, a `hishel` cache sits under the client as a transport and keeps successful responses in SQLite, because the SEC's own cache headers would cache almost nothing; errors are never cached. Tests run on trimmed real responses through a fake SEC that routes by URL, so the whole suite runs offline in under a second.
