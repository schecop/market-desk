# ADR-0004: EDGAR client: client-side rate limiting (aiolimiter) and a dev cache (hishel)

- **Date:** 2026-10-19
- **Status:** accepted
- **Sprint:** 1

## Context
SEC EDGAR is free and has no quota, but it allows **at most 10 requests per second** per user and requires a `User-Agent` with a contact email. Clients that go over the limit get blocked. Cala tells us to slow down with a `429`; EDGAR expects us to stay under the limit on our own. Development (and the RAG ingestion in Sprint 3) will fetch the same filings again and again: a filing never changes once published, so re-downloading it wastes time and the SEC's capacity.

Measured on 2026-10-19: `company_tickers.json` is ~800 KB (10,443 companies) and sends `Cache-Control: max-age=6`; submissions and filing documents send no `Cache-Control` at all; Apple's latest 10-K is ~1.5 MB of HTML.

## Options considered
**Rate limiting**
1. **`aiolimiter`** (`AsyncLimiter(10, 1)`, a leaky bucket): maintained, small, `async with limiter:` before each request. Cons: one more dependency; timing tests would test the library, not us.
2. **A hand-written limiter** (a lock plus a minimum interval): no dependency, testable with a fake clock. Cons: reinvents a solved problem.

**Development cache**
1. **`hishel`** with its `httpx2` integration: plugs in as a transport (`AsyncCacheTransport`), so the client code doesn't change. With `SpecificationPolicy` it follows HTTP caching rules (RFC 9111); with `FilterPolicy` it caches by our own rules. Cons: the SEC's headers (`max-age=6`, or none) mean RFC rules would cache almost nothing, so we need `FilterPolicy`.
2. **A hand-written disk-cache transport**: full control. Cons: more code to maintain.

**A library for the whole client** (considered after the client was built)
1. **`edgartools`** (MIT, active since 2022, 450 releases): company lookup, filings, rate limiting and caching, plus parsing of 10-K/10-Q documents and XBRL financial statements. Cons for *fetching*: heavy dependencies (pandas, pyarrow, lxml...), it requires the old `httpx<0.29` next to our `httpx2`, a synchronous API with global identity (`set_identity`), no transport injection for offline tests, and its own retry and error policy. Rejected for fetching; its parsing is worth a spike in Sprint 3 (see Consequences).

## Decision
`aiolimiter` at 10 requests per second, injected into the client like `sleep` (tests pass an unlimited one). `hishel.httpx2.AsyncCacheTransport` with `FilterPolicy` and SQLite storage, **only when `EDGAR_CACHE_DIR` is set** (development); production and tests run without it. Retries and errors follow the Cala client's pattern (ADR-0003); no shared base class until a third client shows what is really common.

## Consequences
- Easier: the client stays under the SEC's limit by construction, and repeated development runs are instant and offline.
- Harder: a cached submissions file can be stale in development (new filings don't appear): delete the cache dir to refresh.
- Revisit in Sprint 3: `edgartools` for *parsing* (10-K sections for RAG chunks, XBRL financials). Spike question: can it parse a document our client already fetched, or is parsing tied to its own fetching?
- Revisit: if Sprint 3 ingestion needs a production cache, filings (immutable) can be cached forever while submissions need a TTL.
