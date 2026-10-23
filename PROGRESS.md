# Progress Log

Newest entry first. One entry per working session. The plan is in [`docs/PLAN.md`](docs/PLAN.md).

**Current sprint:** Sprint 2 — Agent core (not started; Sprint 1 done, 8 of 8 tasks)
**Hours so far:** ~23 / ~90.5

<!-- Template (copy above the latest entry):
## YYYY-MM-DD · Sprint N · Xh
- **Done:** ...
- **Learned:** key concept(s); details in docs/journal/sprint-N/
- **Next step:** the exact first thing to do next session
- **Blockers / notes:** ...
-->

## 2026-10-23 · Sprint 1 · ~14h (sessions 16-23 Oct)
- **Done:** Sprint 1 finished, PRs #7-#11 plus this one. Cala client (typed, async, error mapping, tenacity retries honouring `Retry-After`; ADR-0003) and EDGAR client (rate limit, dev cache; ADR-0004), tested offline with `MockTransport`. Signed webhooks in and out with Standard Webhooks (ADR-0005). n8n in Docker Compose verifying signatures and posting to Slack, workflows as JSON in the repo. A scheduled check: watchlist and `seen_filings` tables, outbox with at-least-once delivery, baseline on add, lifespan loop; tests on a separate `market_desk_test` database (ADR-0006). Verified live: a "new" Apple 10-K reached Slack, including through an n8n outage. Retrospective written.
- **Learned:** retries and backoff, which errors to retry; dependency injection for testability; rate limiting and caching; HMAC signatures, replay and timing attacks, 401 vs 403; Docker service names vs `localhost`; the outbox pattern, at-least-once delivery and idempotency keys; SQLAlchemy sessions; test isolation with a rolled-back transaction. Details in `docs/journal/sprint-1/`.
- **Next step:** `make up` (rebuilds the image: a stale one fails on the new migration) and `make check`. Then Sprint 2, task 1: start with Claude explaining the plan, on a new branch from `main`. First answer the open question on how Cala adds value over EDGAR (Sprint 1 overview).
- **Blockers / notes:** n8n doesn't deduplicate events yet (a crash between send and commit would post twice). `.env` must use the production URL `/webhook/market-desk`, not `/webhook-test/`. The `api` container's filing check is off unless `FILING_CHECK_INTERVAL_MINUTES > 0`. Working preference from the retro: for a new topic, Claude implements first and Pablo supervises, then Pablo writes the core of the next similar piece.

## 2026-10-14 · Sprint 0 · ~1.5h (evening session)
- **Done:** Sprint 0 finished. Task 8: journal site (MkDocs Material on GitHub Pages, one page per task, review pages, strict builds with anchor checks, `docs.yml` deploying with OIDC), live at https://schecop.github.io/market-desk/ (PR #3). Fix: `make help` failed in Git Bash (PR #4). Task 9: ruleset `protect-main` (PR + both CI checks required, pinned to GitHub Actions, no bypass), created in the UI (PR #5). Task 10: README status, badges and a quick start tested on a fresh clone (PR #6). Retrospective written.
- **Learned:** static sites and strict builds as link checkers; OIDC deploys and job-level permissions; `needs:` vs `if:`; path filters and why a path-filtered check can't be *required*; which shell make uses (`cmd` vs `sh`); rulesets and required checks matched by job name; the fresh-clone test. Details in `docs/journal/sprint-0/` (tasks 8-10).
- **Next step:** Sprint 1, task 1. Before the first model: decide on a separate test database (the stairway test wipes the dev DB; open question in the Sprint 0 overview).
- **Blockers / notes:** task 9's exercise parts 1-2 (shell outputs, the direct-push rejection) were predicted but not run. `ubuntu-latest` moves to Ubuntu 26 on 2026-10-19: if CI turns red for no visible reason, suspect that first. Working preference from the retro: fewer approval stops for steps already done once.

## 2026-10-14 · Sprint 0 · ~7.5h (sessions 10-14 Oct)
- **Done:** Sprint 0 tasks 1-6, merged to `main` in PR #1 with green CI: uv package with `src/` layout and FastAPI `/health` (503 when the DB is down); Postgres + pgvector in Docker Compose; SQLAlchemy sessions and Alembic (first empty migration, stairway test); multi-stage Dockerfile with a one-off `migrate` service (ADR-0001); ruff, mypy strict, pytest warnings-as-errors, pre-commit; `Makefile`; GitHub Actions (lint, types, tests against a Postgres service container, Docker build). Tooling installed: uv, gh, GNU make.
- **Learned:** `src/` layout; connection pools and readiness checks; test isolation (dependency overrides, `lru_cache`, `monkeypatch`, `is` vs `==`); Alembic's version table and why stairway tests end with an upgrade; layer caching, image vs container, container networking; types catch what tests miss; make prerequisites and `.PHONY`; hooks check the commit, CI checks the repo. Details and all exercises in `docs/journal/sprint-0.md`.
- **Next step:** Sprint 0 task 7, journal site (MkDocs Material on GitHub Pages, ADR-0002): start with Claude explaining the plan, on a new branch from `main`. Before that: `make up` and `make check`.
- **Blockers / notes:** Sprint 0 is over its ~5h estimate (~7.5h so far), mostly from guided exercises. Open question in the journal: the stairway test wipes the dev DB, so decide on a separate test database before Sprint 1's first model. `ubuntu-latest` moves to Ubuntu 26 on 2026-10-19: if CI turns red then for no visible reason, suspect that first.

## 2026-10-10 · Planning · 0h (2)
- **Done:** repo published on GitHub (public). Added the learning protocol: `CLAUDE.md` rules (explain before acting, walk through after, journal as you go), `docs/journal/` (template + `sprint-0.md`), PR template, and the "Learning first" section in `docs/PLAN.md`.
- **Learned:** how the learning trace is organised: see `docs/journal/README.md`.
- **Next step:** Sprint 0, first task: create `backend/pyproject.toml` with uv and a FastAPI app with `/health`.
- **Blockers / notes:** none.

## 2026-10-10 · Planning · 0h
- **Done:** repo created with the project guide (`docs/PLAN.md`), `CLAUDE.md`, ADR template, `.env.example`.
- **Next step:** Sprint 0, first task: create `backend/pyproject.toml` with uv and a FastAPI app with `/health`.
- **Blockers / notes:** create the public GitHub repo `market-desk` and push the initial commit (GitHub CLI was not installed when the repo was created).
