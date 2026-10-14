---
tags:
  - postgres
  - docker
  - testing
  - config
---

# 2. Postgres and a readiness check

**Sprint 0** · **Date:** 2026-10-10 · **Plan item:** `docker-compose.yml` with `pgvector/pgvector` Postgres; `/health` checks the DB connection

## What and why
Postgres 16 with pgvector runs in Docker Compose, and `/health` became a real readiness check: 200 when the database answers, 503 when it doesn't. Config moved into a typed `Settings` class, and the DB connection goes through one shared SQLAlchemy engine.

## Decisions
| Date | Decision | Why | Alternatives considered | ADR |
|---|---|---|---|---|
| 2026-10-10 | Compose runs only `db` for now; API runs with `uv run uvicorn` | Fast reload, debugger works; API container comes with the Dockerfile | API service in compose now | — |
| 2026-10-10 | SQLAlchemy engine + psycopg 3 already in task 2 | `/health` shares the app's engine and pool; no throwaway raw-driver code | Raw `psycopg.connect()` in `/health`; asyncpg + async engine | — |
| 2026-10-10 | Sync (not async) DB access | Simpler to learn and debug; FastAPI runs sync handlers in a threadpool, plenty for this load | Async SQLAlchemy + asyncpg (revisit if voice/streaming needs it) | — |
| 2026-10-10 | `/health` returns 503 when DB is down | Load balancers and orchestrators route on status codes, not JSON bodies | Always 200 with a status field | — |
| 2026-10-10 | DB-up test uses the real Postgres, not a mock | Mocking the DB would test nothing; CI gets Postgres as a service container | Mock `database_is_reachable`; skip test when DB absent (hides failures) | — |

## Concepts

### Liveness vs readiness
A liveness check answers "is the process alive?"; a readiness check answers "can it actually serve requests (DB reachable, etc.)?". Since task 2, `/health` is a readiness check: 200 when Postgres answers `SELECT 1`, **503** when it doesn't, so a load balancer (Sprint 7) stops routing traffic to an instance that can't serve it.

### Docker Compose basics
`docker-compose.yml` declares services. `image` = what to run; `environment` = config the image reads on first start (creates user/db); `ports: "5432:5432"` = host:container; a **named volume** (`pgdata`) keeps data when the container is removed (`docker compose down` keeps it, `down -v` deletes it); `healthcheck` lets Docker (and later CI) know when Postgres is actually ready, not just started.

### Engine and connection pool
`create_engine()` doesn't connect; it creates a *pool* that opens connections lazily and reuses them, because opening a Postgres connection is slow (TCP + auth). Create it **once** per process (`@lru_cache` on `get_engine`). `pool_pre_ping=True` checks a pooled connection before handing it out, so after a DB restart the app recovers by itself instead of failing on a dead connection. `connect_timeout` makes a down DB fail in seconds instead of hanging.

### Database URL anatomy
`postgresql+psycopg://user:password@host:port/dbname`. The `+psycopg` part picks the *driver* SQLAlchemy uses (psycopg 3).

### pydantic-settings
A `BaseSettings` class reads each field from an env var of the same name (case-insensitive: `database_url` ← `DATABASE_URL`), then from `.env`, then the default. Real env vars win, which is how Docker/AWS will inject config. Types are validated at startup, so bad config fails immediately.

### FastAPI dependency injection
`engine: Annotated[Engine, Depends(get_engine)]` tells FastAPI to call `get_engine()` and pass the result in. The handler doesn't know where the engine comes from, so tests can swap it: `app.dependency_overrides[get_engine] = lambda: other_engine`. Always clear overrides after the test so they don't leak.

### Test isolation
Every test must pass alone and in any order. Anything shared across tests (module-level objects like `app`, function caches like `@lru_cache`, env vars) can carry state from one test into the next, which creates *order-dependent* tests: green or red depending on the order, not the code. Check by running tests in a different order with explicit node IDs: `pytest a.py::test_x b.py::test_y` runs them in that order.

### `monkeypatch`
A built-in pytest fixture: makes temporary changes at runtime (`setenv`, `delenv`, `setattr`) and undoes them all when the test ends, **even if the test fails**. Safer than writing to `os.environ` directly, which leaks into every later test.

### `lru_cache` and tests
A cached function keeps its result across tests. `get_settings.cache_clear()` empties it; `cache_info()` shows hits and misses. When testing *the thing being cached* (`Settings`), build it directly instead of going through the cache, and there's nothing to clean up.

### `==` vs `is`
`==` compares values (Pydantic models with equal fields are `==`); `is` checks it's the *same object in memory*. "Is it cached?" is an `is` question.

## Code map
| File | What it does | Why it exists / why this way |
|---|---|---|
| `docker-compose.yml` | Started with `db` only (Postgres 16 + pgvector, named volume, healthcheck); `migrate` and `api` added in [task 4](04-dockerfile.md) | Same database locally as in CI and later on AWS |
| `backend/src/market_desk/config.py` | `Settings` (env vars / `.env`) + cached `get_settings()` | One typed place for all config; secrets stay out of code |
| `backend/src/market_desk/db/engine.py` | Cached SQLAlchemy engine + `database_is_reachable()` | One connection pool per process; health logic testable on its own |
| `backend/src/market_desk/api/main.py` | `GET /health` now a readiness check (DB via injected engine) | 503 lets a load balancer stop routing to an instance that can't serve |
| `backend/tests/test_health.py` | Tests `/health` with DB up (real Postgres) and down (overridden engine) | Covers both branches; shows the dependency-override pattern |
| `backend/tests/test_config.py` | Env var beats default; `get_settings()` caches and `cache_clear()` resets it | My exercise; pins down config behaviour the whole app relies on |

## Gotchas
!!! bug "Health test fails with `ArgumentError: Could not parse SQLAlchemy URL`, only when run after the config test"
    **Cause:** the config test went through `get_settings()` with a fake `DATABASE_URL`; the cached `Settings` outlived the test (`monkeypatch` restores env vars, not caches).
    **Fix:** build `Settings()` directly in that test; clear the cache at the start and end of the caching test.
    **Lesson:** caches are shared state; check tests in more than one order.

!!! bug "Every `docker` command returns `500 Internal Server Error ... dockerDesktopLinuxEngine`"
    **Cause:** Docker Desktop's engine crashed.
    **Fix:** quit and reopen Docker Desktop, `docker compose up -d`; data survives in the volume.
    **Lesson:** tell "my code is broken" apart from "my tools are broken".

!!! bug "(avoided) `.env` at repo root ignored when running from `backend/`"
    **Cause:** `env_file` paths are relative to the current directory.
    **Fix:** `env_file=("../.env", ".env")`.
    **Lesson:** relative paths resolve from where you *run*, not where the file lives.

## Check questions
!!! note "Reconstructed"
    These questions were written during the journal migration, from what this task covered; the originals weren't recorded.

??? question "Postgres is stopped. What does `GET /health` return, and why that and not 200 with `{\"db\": \"down\"}`?"
    503. Load balancers and orchestrators decide on the status code, not the body; a 200 would keep sending traffic to an instance that can't serve it.

??? question "You restart the `db` container while the API keeps running. Why does the next `/health` still succeed?"
    `pool_pre_ping=True`: before handing out a pooled connection, SQLAlchemy checks it's alive and replaces it if the old one died with the restart. Without it, the first request after the restart would fail on a dead connection.

??? question "`DATABASE_URL` is set both in `.env` and as a real environment variable. Which one wins?"
    The real environment variable. pydantic-settings reads env vars first, then `.env`, then the default. That's how Docker and AWS inject config without touching files.

??? question "Why can a test be green alone and red when run after another test?"
    Shared state leaking between tests: a `dependency_overrides` entry that wasn't cleared, an `lru_cache` holding a `Settings` built from a fake env var, an env var written directly to `os.environ`. Fix the leak (use `monkeypatch`, clear overrides and caches) and check by running tests in a different order.

## Guided exercise
**Task (type):** shared by tasks 1-2. A: remove `dependency_overrides.clear()`, predict and run the tests in reverse order (predict/verify). B: write `tests/test_config.py`: an env var overrides the default, and `get_settings()` caches (write a missing test).

**Outcome:** done: 4 tests pass in every order (2026-10-11).

**What I got wrong:** didn't know `monkeypatch`; used `get_settings()` where a fresh `Settings()` was needed (order-dependent, then polluted the cache for the health test); used `==` to check "same object"; in A, blamed the fake URL instead of the leaked dependency override.

**Lesson:** shared state (app overrides, caches, env) leaks between tests; test the object directly, not through the cache; `is` for identity.

## Explain it in 2 minutes
Postgres runs in Docker Compose with a named volume, so data survives container restarts, and a healthcheck so other things can wait until it's really ready. The API reads its config from a typed `Settings` class (env vars first, then `.env`), and talks to the DB through one cached SQLAlchemy engine: a connection pool created once per process, with pre-ping so it heals after a DB restart and a timeout so a dead DB fails fast. `/health` is a readiness check: it runs `SELECT 1` and returns 503 when that fails, because load balancers route on status codes. The engine is injected with FastAPI's `Depends`, so a test can swap in a broken engine to test the 503 branch, while the happy path runs against the real Postgres. The main lesson was test isolation: caches and overrides are shared state, and tests have to pass in any order.
