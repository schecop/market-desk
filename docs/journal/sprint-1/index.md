# Sprint 1 — Integrations layer

**Dates:** 2026-10-16 → 2026-10-23 · **Hours:** ~14h (estimate ~10h) · **Plan:** [PLAN.md, Sprint 1](../../PLAN.md#8-sprints)

## Goal (in my own words)
Typed, production-grade clients for the two data sources (Cala and SEC EDGAR), plus inbound and outbound webhooks. Integrations are where real systems break: auth, retries, rate limits, pagination and signatures.

## Tasks
| # | Task | Page |
|---|---|---|
| 1 | Cala sign-up, API docs, key in `.env` | [link](01-cala-signup.md) |
| 2 | `clients/cala.py`: typed async client | [link](02-cala-client.md) |
| 3 | `clients/edgar.py`: SEC EDGAR client | [link](03-edgar-client.md) |
| 4 | Unit tests with `MockTransport` | Done inside tasks 2 and 3 ([Cala](02-cala-client.md#code-map), [EDGAR](03-edgar-client.md#code-map)) |
| 5 | `webhooks/`: inbound verification, outbound dispatcher | [link](05-webhooks.md) |
| 6 | n8n in Docker Compose; flow from a "new 10-K" event to Slack | [link](06-n8n-slack.md) |
| 7 | Scheduled check for new watchlist filings, firing the outbound webhook | [link](07-filing-check.md) |

## Sprint-level decisions
| Date | Decision | Why | Alternatives considered | ADR |
|---|---|---|---|---|
| 2026-10-16 | Treat Cala's free tier (100 calls in total) as a hard budget: tests always mock it (`MockTransport`), development uses a local response cache, live calls only on purpose | 100 calls run out in one careless afternoon of debugging; once spent, the integration can't be checked | Call the live API while developing (burns the quota); a paid tier (outside the budget) | [ADR-0003](../../adr/0003-http-client-design.md) |
| 2026-10-19 | Version the editor setup: `.vscode/settings.json` (interpreter, Ruff, mypy, pytest pointed at `backend/`) and `.vscode/extensions.json` (Python, Pylance, Ruff, Mypy); everything else in `.vscode/` stays ignored | The uv venv lives in `backend/`, so VS Code didn't find it and there was no autocomplete or go-to-definition; versioning the fix makes every clone behave the same, and the editor runs the same ruff/mypy versions and config as CI | Configure by hand each time (not reproducible); a multi-root `.code-workspace` (one more file to remember to open); Dev Containers (too much for now) | — |

## Open questions
- [x] Stairway test runs `downgrade base` on the **dev** DB (carried over from [Sprint 0](../sprint-0/index.md#open-questions)). **Decided in task 7:** tests use their own `market_desk_test` database, created by `conftest.py` ([ADR-0006](../../adr/0006-filing-alerts-outbox-and-test-database.md)).
- [x] Cala pagination: no cursor anywhere. `GET /v1/entities` has only `limit` (max 100); relationships on `POST /v1/entities/{id}` use `limit`/`offset`. See [task 1](01-cala-signup.md#what-the-cala-api-looks-like).
- [ ] Is a `429` from Cala "too fast" or "quota spent"? Still unknown (no live call spent on it). Either way the client is bounded: at most 3 attempts, and a `Retry-After` over 30 s fails fast.

## Concepts (outside a task)

### Language server (LSP)
The editor doesn't understand code by itself. Highlighting by meaning (function vs class vs variable), autocomplete, hover docs, go-to-definition (`F12` / `Ctrl+click`) and type errors come from a separate process, the *language server*, which the editor talks to through the Language Server Protocol (LSP). For Python that server is Pylance; for TypeScript it's `tsserver`. To resolve `import httpx` the server has to know **which interpreter** you use, because that interpreter's `site-packages` is where the libraries are. If no interpreter is selected, or VS Code can't find the venv (here it's in `backend/.venv`, not at the repo root), imports show as unresolved and autocomplete stops at the standard library. Fix: install the language server and point it at the venv (`python.defaultInterpreterPath`, or "Python: Select Interpreter").

- [ ] **For Sprint 3:** try `edgartools` for *parsing* (10-K sections, XBRL financials) on documents our client already fetched. See [ADR-0004](../../adr/0004-edgar-rate-limit-and-dev-cache.md#consequences).

- [ ] **For Sprint 2:** how Cala adds value over EDGAR alone: which questions need its verified facts and relationships, and which a 10-K already answers. Check it before wiring the agent's tools.

## Retrospective (at sprint end)
**What I built:** two typed API clients, one for Cala and one for SEC EDGAR, both with retries and backoff, custom errors and the headers each API requires; and a workflow that watches EDGAR for new filings of the watchlist companies, records them in the database, and sends a Slack message through n8n.

**A decision and why:** don't reinvent the wheel for hard problems: tenacity for retries, the Standard Webhooks spec and its library for signatures, n8n for routing. Maintenance is easier, and future integrations hook into protocols other tools already speak.

**A problem and how I solved it:** I didn't see the point of some pieces of the plan at first (the inbound webhook, n8n, the outbox). Elaborating, implementing and questioning them gave me a clear picture of how the pieces connect. I still need a closer look at how Cala adds value here.

**What I'd do differently:** implementing a completely new topic from scratch costs a lot of hours. Better: let Claude implement the first one while I supervise and question everything, then do the core of a similar piece myself (as with the Cala client, then EDGAR). Sprint 1 took ~14h against a ~10h estimate (~1.4×, like Sprint 0).
