---
tags:
  - integrations
  - database
  - reliability
---

# 7. Scheduled check for new filings

**Sprint 1** · **Date:** 2026-10-23 · **Plan item:** A scheduled check (simple background task) that detects new filings for watchlist companies and fires the outbound webhook

## What and why
The piece that ties Sprint 1 together: on a timer, the API reads the watchlist from Postgres, asks EDGAR for each company's recent 10-Ks, records the ones it hasn't seen, and sends a signed `filing.created` event for each through the dispatcher, which n8n turns into a Slack message. It brought the first real tables, so tests moved to their own database first.

## Decisions
| Date | Decision | Why | Alternatives considered | ADR |
|---|---|---|---|---|
| 2026-10-23 | Tests use a separate `market_desk_test` database, created and migrated by `conftest.py` | The migration test's `downgrade base` would wipe dev data | Migration test only in CI; a Postgres init script (runs only on a fresh volume) | [ADR-0006](../../adr/0006-filing-alerts-outbox-and-test-database.md) |
| 2026-10-23 | `seen_filings` as an outbox: insert with `notified_at` NULL, send, then mark | At-least-once: an outage or crash repeats an alert, never loses one | A `last_accession` column; mark before sending (at-most-once) | [ADR-0006](../../adr/0006-filing-alerts-outbox-and-test-database.md) |
| 2026-10-23 | Event id `msg_<accession number>` | Same filing, same id, across attempts and runs: receivers can dedupe | A random id per event (every retry looks new) | [ADR-0006](../../adr/0006-filing-alerts-outbox-and-test-database.md) |
| 2026-10-23 | Baseline on add: existing filings stored as already notified | Otherwise adding AAPL alerts on its last 10 annual reports | Alert on everything; compare dates (fragile) | [ADR-0006](../../adr/0006-filing-alerts-outbox-and-test-database.md) |
| 2026-10-23 | Link `seen_filings` to the watchlist by CIK, no foreign key | CIK isn't unique on the watchlist (GOOG and GOOGL) | A foreign key to the watchlist row | |
| 2026-10-23 | An `asyncio` loop in the API's lifespan, off by default; plus a one-off command | "A simple background task" with no new dependency; off so tests and `make dev` never call EDGAR on their own | APScheduler; n8n's Schedule trigger calling the API (logic split across two places) | |
| 2026-10-23 | The check's EDGAR client skips the dev cache | A cached submissions list would never show a new filing | Clear the cache before each run (easy to forget) | |
| 2026-10-23 | `get_company` returns ticker, CIK and name from one dict built at parse time | Slack shows the name; one dict instead of two parallel ones | A second dict of names next to the CIKs | |

## Concepts
### The outbox pattern
To do two things that can't share one transaction (write to the database, call another system), write the intent to a table **first**, in your own transaction, then do the call, then mark the row done. A crash at any point leaves a row that says what's still pending, and the next run finishes it. Here `seen_filings` is the outbox and `notified_at IS NULL` means "still to send".

### At-least-once vs at-most-once delivery
If you mark a message sent **after** sending, a crash in between sends it again: **at-least-once** (possible duplicates, never lost). If you mark it **before**, a crash loses it: **at-most-once**. Exactly-once delivery doesn't exist across a network; "effectively once" is at-least-once plus a receiver that deduplicates by a stable id.

### Idempotency keys, from the sender's side
In task 5 the receiver deduplicated by `webhook-id`. That only works if the sender gives a repeat **the same** id. A random id per attempt defeats it; an id derived from the thing itself (`msg_<accession number>`) makes every repeat recognisable, even across process restarts.

### Baselining a new watch
When you start watching something, decide what counts as "new". Recording what already exists as already handled means only changes after that moment alert. Without it, the first run treats all history as new.

### FastAPI lifespan
An async context manager passed to `FastAPI(lifespan=...)`: code before `yield` runs at startup, code after it at shutdown. Here it starts the check loop as an `asyncio` task and cancels it cleanly on shutdown. `TestClient(app)` used as a `with` block runs both, which is how the tests check it.

### SQLAlchemy sessions: select, add, change, commit
The session collects changes and sends them on `commit()`. Read with `session.scalars(select(Model).where(...))` (`.all()`, or `session.scalar(...)` for the first row or `None`); `IS NULL` is `.is_(None)`. Insert with `session.add(obj)`. Update by changing an attribute of a loaded object: the session notices and writes the `UPDATE` on commit.

### Test isolation with a rolled-back transaction
Each test's session runs inside an outer transaction that is rolled back at the end. The code under test can still `commit()`: with `join_transaction_mode="create_savepoint"` its commits become savepoints inside the outer transaction, so the rollback undoes them too. Tests stay independent with no cleanup code.

## Code map
| File | What it does | Why it exists / why this way |
|---|---|---|
| `backend/tests/conftest.py` | Points `DATABASE_URL` at `market_desk_test`, creates it if missing, migrates it once; `db_session` rolls back each test | Tests never touch dev data |
| `backend/src/market_desk/db/models.py` | `WatchlistEntry`, `SeenFiling` | The first real tables |
| `backend/src/market_desk/db/migrations/versions/..._watchlist_and_seen_filings.py` | Creates both tables | Autogenerated, constraint names from the naming convention |
| `backend/src/market_desk/clients/edgar.py` | `Company` and `get_company` (written by me); `get_cik` built on it | The name for Slack |
| `backend/src/market_desk/watchlist.py` | `add` (with baseline), `remove`, `list`, and the command | How companies get on the watchlist until Sprint 2's tools |
| `backend/src/market_desk/jobs/filings.py` | `check_new_filings` (written by me), `filing_event_id` | The core: record, then send, then mark |
| `backend/src/market_desk/jobs/check_filings.py` | `run_check_once` (real clients, no dev cache), `filing_check_loop`, the command | Wiring and the timer |
| `backend/src/market_desk/api/main.py` | `lifespan` starts and stops the loop | Off unless `FILING_CHECK_INTERVAL_MINUTES > 0` |
| `backend/src/market_desk/config.py` | `filing_check_interval_minutes` (≥ 0, default 0) | |
| `docker-compose.yml`, `.env.example` | The `api` container gets `N8N_WEBHOOK_URL: http://n8n:5678/...` and the check's settings | Service names inside Docker |
| `backend/tests/fakes.py` | A fake SEC and a fake n8n | Shared by the check and watchlist tests |
| `backend/tests/test_check_filings.py`, `test_watchlist.py`, `test_lifespan.py` | 5 + 5 + 2 tests | New filing sent; nothing new; failed delivery retried with the same id; one company's EDGAR error doesn't stop others; one CIK, one event; baseline; startup wiring |

## Gotchas
!!! bug "`limit=0` returned no filings"
    **Symptom:** (caught in review) the check would never find anything.
    **Cause:** `list_filings` ends with `filings[:limit]`, and `[:0]` is an empty list.
    **Fix:** keep the default (10 most recent).
    **Lesson:** "0 means no limit" is a convention some APIs use, not a Python one; read what the function does with the value.

!!! bug "Ticker and name from two queries could come from different rows"
    **Symptom:** (caught in review) two separate `session.scalar(...)` calls for ticker and name, without an order.
    **Cause:** with two watchlist rows for one CIK, Postgres may return them in any order, so the ticker of one row could pair with the name of the other; and `None` (company removed while a filing was pending) crashed the whole run.
    **Fix:** load one `WatchlistEntry`, ordered by ticker; skip the filing (with a log line) if it's `None`.
    **Lesson:** without `ORDER BY`, a database promises no order; and anything that can be `None` will be, eventually: mypy's `union-attr` error was pointing at it.

!!! bug "A leftover loop variable in a log line"
    **Symptom:** (caught in review) `print(f"CIK {cik} ...")` in step 2 used `cik` from step 1's loop.
    **Cause:** Python loop variables outlive their loop; it held the last CIK of step 1, and with an empty watchlist it wouldn't exist at all (`NameError`).
    **Fix:** `pending_filing.cik`, through `logger.info`.
    **Lesson:** reusing a name from an earlier loop is a classic source of wrong-but-plausible output.

!!! bug "Wrong field names in the SEC tickers file"
    **Symptom:** 18 tests failed with `EdgarResponseError: Unexpected tickers file`.
    **Cause:** `c["cik"]` and `c["name"]`; the file uses `cik_str` and `title`.
    **Fix:** the real names.
    **Lesson:** check field names against the fixture, not memory; and the `except` that turns a `KeyError` into a clear `EdgarResponseError` did its job.

## Check questions
??? question "`dispatcher.send(event)` succeeds, then the process crashes before `session.commit()`. What happens next?"
    `notified_at` is still NULL, so the next run sends it again: Slack gets it **twice**. That's acceptable because the alternative, marking before sending, turns a crash into a lost alert. Both deliveries carry the same `msg_<accession>` id, so a receiver that remembers ids can make it "effectively once"; our n8n flow doesn't deduplicate yet. *(I first called the send "idempotent": it isn't; the design is at-least-once, and the stable id is what makes deduplication possible.)*

??? question "What would the first check after `add AAPL` do without the baseline?"
    Announce every 10-K `list_filings` returns, the 10 most recent: ten Slack messages, about ten years of annual reports, at once.

## Guided exercise
**Task (written by me):** `Company` / `get_company` in the EDGAR client, and `check_new_filings`, against tests written first. Then, live: stop n8n, predict, run the check, start n8n, run it again.

**Outcome:** 102 tests green after review fixes. Live against EDGAR: adding AAPL baselined its recent 10-Ks (the first check announced nothing); deleting the newest 10-K from `seen_filings` made the next check announce it to Slack. With n8n stopped, the filing was recorded with `notified_at` NULL, the dispatcher tried 3 times and gave up, and the row waited; with n8n back, the next run delivered it and Slack got exactly one message.

**What I got wrong:** I had no SQLAlchemy experience and needed a guide to the session. Review found the issues in Gotchas; mypy found two of them on its own.

**Lesson:** the order "record → send → mark" is the whole reliability design; each commit's position decides what a crash can lose.

## Explain it in 2 minutes
Every N minutes the API runs a check. It reads the distinct CIKs on the watchlist, asks EDGAR for each company's recent 10-Ks, and inserts any accession number it hasn't seen into `seen_filings`, with `notified_at` empty, then commits. That table is an outbox. Then it sends a signed `filing.created` event for every row still unsent, and only after the receiver answers 2xx does it set `notified_at` and commit. So if n8n is down or the process dies, the row stays pending and the next run retries it: delivery is at-least-once, never lost, and each event's id comes from the accession number, so a repeat is recognisable and can be deduplicated. Adding a company baselines it, so its history doesn't alert. One company's EDGAR error doesn't stop the others. The timer is an asyncio task started by FastAPI's lifespan and off by default; there's also a one-off command. Tests run against a separate database, inside a transaction rolled back after each test, so even the code's own commits disappear.
