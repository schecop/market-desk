# ADR-0006: Filing alerts: outbox table, at-least-once delivery, and a separate test database

- **Date:** 2026-10-23
- **Status:** accepted
- **Sprint:** 1

## Context
Sprint 1 ends with an alert: when a watchlist company files a new 10-K, an event goes to n8n, which posts to Slack. That needs the first real tables (watchlist, filings we've seen) and a rule for what happens when delivery fails or the process dies halfway. It also forced an open question from Sprint 0: the migration test runs `downgrade base`, which would wipe the new tables in the dev database.

## Options considered
1. **Remember only the last filing per company** (a `last_accession` column on the watchlist): one table, but no history, no record of what was delivered, and a failed send is either lost or re-detected by luck.
2. **An outbox table, `seen_filings`, with `notified_at`**: every filing found is inserted (unique accession number) with `notified_at` NULL, sent, then marked. Anything still NULL is retried on the next run. Delivery is **at-least-once**: a crash between send and commit repeats an alert, never loses one.
3. **Mark before sending (at-most-once)**: no duplicates, but a crash or an n8n outage loses the alert silently.

For the test database: (a) run the migration test only in CI (loses the local safety net), (b) a Postgres init script (only runs on a fresh volume, so existing setups never get it), (c) **`conftest.py` creates `market_desk_test` if missing** and points `DATABASE_URL` at it before the app reads its settings.

## Decision
Option 2, with event ids derived from the accession number (`msg_<accession>`) so repeats carry the same id and receivers can deduplicate. A company is **baselined** when added: its existing filings are stored as already notified, so only later filings alert. The check runs in an `asyncio` loop started by the API's lifespan (off by default), and as a one-off command. Tests use a separate `market_desk_test` database created by `conftest.py`; each test's changes, commits included, are rolled back.

## Consequences
- Alerts survive n8n outages and crashes; the cost is a possible duplicate. n8n doesn't deduplicate yet, so a duplicate would reach Slack.
- `seen_filings` is linked to the watchlist by CIK without a foreign key, because two tickers can share a CIK (GOOG, GOOGL).
- With several API instances, each would run the loop; the unique accession number prevents duplicate rows, not duplicate sends. In AWS (Sprint 7) the check becomes one scheduled task.
- The check uses a sync session inside async code: fine at this scale; SQLAlchemy's async engine if it grows.
- Sprint 2 adds clients: the watchlist gets a client id through a new migration.
