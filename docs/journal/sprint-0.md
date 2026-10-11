# Sprint 0 — Scaffold

**Dates:** 2026-10-10 → · **Hours:** ~2h · **Plan:** [docs/PLAN.md, Sprint 0](../PLAN.md#sprint-0--scaffold-4h)

## Goal (in my own words)
A clean, professional skeleton every later sprint builds on: an installable Python package, a FastAPI service backed by Postgres in Docker, automated lint/type/test checks, and CI on every PR. Everything later depends on it.

## Decisions log
| Date | Decision | Why | Alternatives considered | ADR |
|---|---|---|---|---|
| 2026-10-10 | Standalone public repo outside OneDrive (`C:\Users\pablo\PP\market-desk`) | OneDrive syncing `.venv`, `node_modules` and Docker volumes causes slowness and file locks; GitHub is the backup | Inside an existing workspace folder; OneDrive folder | — |
| 2026-10-10 | Learning protocol in `CLAUDE.md` (explain before acting, walk through after, journal everything) | This is a learning project: understanding and a re-readable trace matter more than speed | Let Claude generate freely and review at the end | — |
| 2026-10-10 | uv with `uv init --package` and a `src/` layout; Python pinned to 3.12 | One tool for Python version, venv, deps and lockfile; `--package` makes the code an installable package so tests import it like a user would | Poetry; pip + venv + requirements.txt; flat layout | — (in stack table) |
| 2026-10-10 | `pytest` + `httpx2` as a dev dependency group, not runtime deps | Test-only tools shouldn't ship in the production image; Starlette's TestClient now expects `httpx2` | Put them in `dependencies`; keep `httpx` and live with the deprecation warning | — |
| 2026-10-10 | App lives in `market_desk/api/main.py`, not the package root | Matches the repo layout in PLAN section 7: `api/` is one layer next to `clients/`, `agent/`, etc. | Single `main.py` at package root | — |
| 2026-10-10 | `.gitattributes` with `eol=lf` | Code runs on Linux (Docker, CI, AWS); CRLF breaks shell scripts and Makefiles; per-repo file beats each machine's `core.autocrlf` | Rely on everyone's git config | — |
| 2026-10-10 | Compose runs only `db` for now; API runs with `uv run uvicorn` | Fast reload, debugger works; API container comes with the Dockerfile | API service in compose now | — |
| 2026-10-10 | SQLAlchemy engine + psycopg 3 already in task 2 | `/health` shares the app's engine and pool; no throwaway raw-driver code | Raw `psycopg.connect()` in `/health`; asyncpg + async engine | — |
| 2026-10-10 | Sync (not async) DB access | Simpler to learn and debug; FastAPI runs sync handlers in a threadpool, plenty for this load | Async SQLAlchemy + asyncpg (revisit if voice/streaming needs it) | — |
| 2026-10-10 | `/health` returns 503 when DB is down | Load balancers and orchestrators route on status codes, not JSON bodies | Always 200 with a status field | — |
| 2026-10-10 | DB-up test uses the real Postgres, not a mock | Mocking the DB would test nothing; CI gets Postgres as a service container | Mock `database_is_reachable`; skip test when DB absent (hides failures) | — |

## Concepts
**`pyproject.toml`**: the one standard file (PEP 621) that describes a Python project. `[project]` holds metadata and *runtime* dependencies (what the app needs to run). `[dependency-groups]` holds *dev-only* groups (tests, linters) that never get installed in production. `[build-system]` says which tool turns the source into an installable package (here `uv_build`).

**`uv.lock`**: the exact resolved version of every package, transitive ones included. `pyproject.toml` says `fastapi>=0.143.0` (a range); the lock says exactly which version. Commit it so CI, Docker and your laptop install identical environments. `uv sync` installs from it; `uv add` updates both files.

**`src/` layout**: the package lives in `backend/src/market_desk/`, not `backend/market_desk/`. Python can't import it just because it's in the current folder; it has to be *installed* (uv installs it in editable mode into `.venv`). That way tests exercise the package the way a real user would, and a missing file or a broken package config fails in tests instead of in production.

**`uv run` auto-syncs**: before running a command, `uv run` checks `.venv` against `uv.lock` and creates/updates it if needed. Deleting `.venv` is harmless: the next `uv run` rebuilds it identically.

**Why `src/` prevents "works on my machine"**: without `src/`, Python puts the current directory on `sys.path`, so `import market_desk` finds the loose source folder even if the package was never installed or is misconfigured. Tests pass locally and packaging bugs only appear where the package is really installed (Docker, CI). With `src/`, the only way the import works is through the installed package, so those bugs fail in tests first.

**ASGI / uvicorn / FastAPI**: FastAPI is a framework: it maps URLs to Python functions and validates input/output. It doesn't listen on a port itself. Uvicorn is the *ASGI server*: it opens the socket, speaks HTTP, and calls the app object. `uvicorn market_desk.api.main:app` means "import the module `market_desk.api.main`, take the variable `app`".

**Return type annotations in FastAPI**: `-> dict[str, str]` isn't decoration. FastAPI uses it to validate the response and to document it in the OpenAPI schema (`/docs`, `/openapi.json`). In Sprint 4 that schema generates the frontend's TypeScript types.

**`TestClient`**: calls the app *in-process*: no server, no port, no network. It's fast and deterministic, and it's what lets CI test endpoints without starting uvicorn.

**Liveness vs readiness**: a liveness check answers "is the process alive?"; a readiness check answers "can it actually serve requests (DB reachable, etc.)?". Since task 2, `/health` is a readiness check: 200 when Postgres answers `SELECT 1`, **503** when it doesn't, so a load balancer (Sprint 7) stops routing traffic to an instance that can't serve it.

**Docker Compose basics**: `docker-compose.yml` declares services. `image` = what to run; `environment` = config the image reads on first start (creates user/db); `ports: "5432:5432"` = host:container; a **named volume** (`pgdata`) keeps data when the container is removed (`docker compose down` keeps it, `down -v` deletes it); `healthcheck` lets Docker (and later CI) know when Postgres is actually ready, not just started.

**Engine and connection pool**: `create_engine()` doesn't connect; it creates a *pool* that opens connections lazily and reuses them, because opening a Postgres connection is slow (TCP + auth). Create it **once** per process (`@lru_cache` on `get_engine`). `pool_pre_ping=True` checks a pooled connection before handing it out, so after a DB restart the app recovers by itself instead of failing on a dead connection. `connect_timeout` makes a down DB fail in seconds instead of hanging.

**Database URL anatomy**: `postgresql+psycopg://user:password@host:port/dbname`. The `+psycopg` part picks the *driver* SQLAlchemy uses (psycopg 3).

**pydantic-settings**: a `BaseSettings` class reads each field from an env var of the same name (case-insensitive: `database_url` ← `DATABASE_URL`), then from `.env`, then the default. Real env vars win, which is how Docker/AWS will inject config. Types are validated at startup, so bad config fails immediately.

**FastAPI dependency injection**: `engine: Annotated[Engine, Depends(get_engine)]` tells FastAPI to call `get_engine()` and pass the result in. The handler doesn't know where the engine comes from, so tests can swap it: `app.dependency_overrides[get_engine] = lambda: other_engine`. Always clear overrides after the test so they don't leak.

**Test isolation**: every test must pass alone and in any order. Anything shared across tests (module-level objects like `app`, function caches like `@lru_cache`, env vars) can carry state from one test into the next, which creates *order-dependent* tests: green or red depending on the order, not the code. Check by running tests in a different order with explicit node IDs: `pytest a.py::test_x b.py::test_y` runs them in that order.

**`monkeypatch`** (built-in pytest fixture): makes temporary changes at runtime (`setenv`, `delenv`, `setattr`) and undoes them all when the test ends, **even if the test fails**. Safer than writing to `os.environ` directly, which leaks into every later test.

**`lru_cache` and tests**: a cached function keeps its result across tests. `get_settings.cache_clear()` empties it; `cache_info()` shows hits and misses. When testing *the thing being cached* (`Settings`), build it directly instead of going through the cache, and there's nothing to clean up.

**`==` vs `is`**: `==` compares values (Pydantic models with equal fields are `==`); `is` checks it's the *same object in memory*. "Is it cached?" is an `is` question.

**pytest fixtures**: a function decorated with `@pytest.fixture` that tests request by parameter name. Code before `yield` is setup, after `yield` is teardown (runs even if the test fails).

## Code map
| File | What it does | Why it exists / why this way |
|---|---|---|
| `docs/PLAN.md` | The project guide | Restart from any point without context |
| `CLAUDE.md` | Rules for Claude Code sessions | Tutor mode + learning protocol |
| `PROGRESS.md` | Session log | Where we are and the next step |
| `docs/journal/` | Learning trace per sprint | Decisions, concepts, code map, bugs, kept for later |
| `backend/pyproject.toml` | Project metadata, runtime deps, dev group, build backend | Single source for deps and (soon) tool config |
| `backend/uv.lock` | Exact pinned versions of every dependency | Reproducible installs locally, in CI and in Docker |
| `backend/.python-version` | Pins Python 3.12 for uv | Everyone (and CI) runs the same interpreter |
| `backend/src/market_desk/api/main.py` | FastAPI `app` + `GET /health` (readiness, uses DB) | Entry point uvicorn serves; home of all routers later |
| `backend/tests/test_health.py` | Tests `/health` with DB up (real Postgres) and down (overridden engine) | Covers both branches; shows the dependency-override pattern |
| `backend/tests/test_config.py` | Env var beats default; `get_settings()` caches and `cache_clear()` resets it | My exercise; pins down config behaviour the whole app relies on |
| `.gitattributes` | Forces LF line endings for every clone | Linux-bound code must not get CRLF |
| `docker-compose.yml` | Local Postgres 16 + pgvector with volume and healthcheck | Same DB locally as in CI and (RDS) in AWS |
| `backend/src/market_desk/config.py` | `Settings` (env vars / `.env`) + cached `get_settings()` | One typed place for all config; secrets stay out of code |
| `backend/src/market_desk/db/engine.py` | Cached SQLAlchemy engine + `database_is_reachable()` | One connection pool per process; health logic testable on its own |

## Gotchas and bugs
| Symptom | Cause | Fix | Lesson |
|---|---|---|---|
| `StarletteDeprecationWarning: Using httpx with starlette.testclient is deprecated` | Recent Starlette moved its TestClient to the `httpx2` package | `uv remove --dev httpx && uv add --dev httpx2` | Read warnings: they tell you about upcoming breakage. `httpx` itself is still what we'll use for API clients in Sprint 1 |
| `uv`/`gh` "command not found" right after installing | The terminal was opened before the install changed PATH | Open a new terminal | PATH is read when a shell starts |
| "LF will be replaced by CRLF" warnings on `git add` | `core.autocrlf=true` (Git for Windows default) converts line endings in the working copy | `.gitattributes` with `* text=auto eol=lf` | Line endings are a repo setting, not a personal one |
| Health test fails with `ArgumentError: Could not parse SQLAlchemy URL` only when run after the config test | Config test went through `get_settings()` with a fake `DATABASE_URL`; the cached `Settings` outlived the test (`monkeypatch` restores env vars, not caches) | Build `Settings()` directly in that test; clear the cache at start and end of the caching test | Caches are shared state; check tests in more than one order |
| (avoided) `.env` at repo root ignored when running from `backend/` | `env_file` paths are relative to the current directory | `env_file=("../.env", ".env")` | Relative paths resolve from where you *run*, not where the file lives |

## Exercises
| Date | Task (type) | Outcome | What I got wrong | Lesson |
|---|---|---|---|---|
| 2026-10-11 | Tasks 1-2. A: remove `dependency_overrides.clear()`, predict and run tests in reverse order (predict/verify). B: write `tests/test_config.py`, env var overrides default + `get_settings()` caching (write a missing test) | Done: 4 tests pass in every order | Didn't know `monkeypatch`; used `get_settings()` where a fresh `Settings()` was needed (order-dependent, then polluted the cache for the health test); used `==` to check "same object"; in A, blamed the fake URL instead of the leaked dependency override | Shared state (app overrides, caches, env) leaks between tests; test the object directly, not through the cache; `is` for identity |

## Commands and snippets worth keeping
```bash
cd backend
uv sync                                              # create .venv from uv.lock
uv add <pkg> / uv add --dev <pkg>                    # add runtime / dev dependency
uv run pytest -q                                     # run tests inside the venv
uv run uvicorn market_desk.api.main:app --reload     # dev server on :8000, docs at /docs

docker compose up -d                                 # start Postgres (from repo root)
docker compose ps                                    # status + health
docker compose exec db psql -U market_desk           # SQL shell inside the container
docker compose stop db / start db                    # simulate an outage
docker compose down        # remove containers, keep data;  down -v also deletes the volume
```

## Open questions
- [ ] ...

## Retrospective (at sprint end)
