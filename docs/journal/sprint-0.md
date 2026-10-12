# Sprint 0 — Scaffold

**Dates:** 2026-10-10 → · **Hours:** ~3.5h · **Plan:** [docs/PLAN.md, Sprint 0](../PLAN.md#sprint-0--scaffold-65h)

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
| 2026-10-11 | Dockerfile + `api` Compose service in Sprint 0 (moved forward from Sprint 7), right after Alembic | Makes "Done when" true; container issues surface while the app is tiny; one command starts the whole stack | Keep it in Sprint 7 and reword "Done when" | [ADR-0001](../adr/0001-containerise-api-in-sprint-0.md) |
| 2026-10-11 | Alembic config in `pyproject.toml` (`pyproject` template); `alembic.ini` keeps only logging | All tool config in one file; no DB URL in a committed file | `generic` template with everything in `alembic.ini` | — |
| 2026-10-11 | Migrations inside the package (`src/market_desk/db/migrations/`) | Matches PLAN layout; shipped with the code into the Docker image | `backend/alembic/` next to `src/` | — |
| 2026-10-11 | `env.py` reads the URL from `get_settings()` | App and migrations can never target different DBs; no credentials in `alembic.ini` | `sqlalchemy.url` in `alembic.ini`; separate env var for Alembic | — |
| 2026-10-11 | Constraint naming convention on `Base.metadata` | Predictable names (`pk_x`, `uq_x_col`) so later migrations can alter/drop constraints | Let Postgres generate names | — |
| 2026-10-11 | First migration empty; pgvector extension deferred to Sprint 3 | Learn the mechanism first; enable things when they're used | `CREATE EXTENSION vector` in the first migration | — |
| 2026-10-12 | Stairway test uses `Config("")` + `script_location="market_desk:db:migrations"` (package notation) | Works from any working directory, via the installed package | `Config(toml_file="pyproject.toml")`: reuses real config but path is relative to cwd | — |
| 2026-10-12 | Journal published as a site: MkDocs Material on GitHub Pages, one page per task; new Sprint 0 task right after CI | Searchable, visual journal for review; same Markdown as the *Record* step, so nothing to keep in sync; free | Plain Markdown on GitHub; a separate page outside the repo | [ADR-0002](../adr/0002-journal-site-mkdocs-github-pages.md) |

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

**Session (unit of work)**: a SQLAlchemy `Session` tracks the objects you load, add and change, and writes them all in one transaction on `commit()` (or throws them away on `rollback()`/close). `sessionmaker` is the factory; `get_session()` gives each request its own session and always closes it. `expire_on_commit=False` keeps objects usable after commit (no surprise reload, no error once the session is closed).

**Generator dependencies**: a FastAPI dependency with `yield` runs up to `yield`, hands the value to the route, then resumes after the response: the code after `yield` (or the `with` exit) is the cleanup. Same shape as a pytest fixture. You can drive one by hand: `next(gen)` = setup, exhaust it = teardown.

**`DeclarativeBase` and metadata**: every model class inherits from `Base`; `Base.metadata` is the registry of all tables. Alembic's `--autogenerate` diffs that registry against the real DB, so models must be imported in `env.py` or autogenerate thinks they don't exist.

**Naming conventions**: constraints (primary key, unique, foreign key, index, check) have names in Postgres. Migrations refer to them by name (`op.drop_constraint("uq_watchlist_ticker", ...)`), so names must be predictable. `MetaData(naming_convention=...)` makes SQLAlchemy name them; Alembic's `op.create_table` uses the same convention, as `\d watchlist` showed (`pk_watchlist`, `uq_watchlist_ticker`).

**Migrations (Alembic)**: the version history of the schema. Each file has `revision`, `down_revision` (its parent, which forms a chain), `upgrade()` and `downgrade()`. The DB stores **one row** in `alembic_version`: the revision it's at. Alembic compares that with the chain to decide what to run, and **never looks at the real tables**. If they disagree (manual changes, a broken `downgrade()`), later migrations crash. Postgres runs DDL inside transactions, so a failing migration rolls back cleanly. Commands: `upgrade head`, `downgrade -1`, `downgrade base`, `current`, `history`, `revision -m`, `revision --autogenerate` (always review its output).

**Migration rules of thumb**:
- A migration is frozen history: never import app code (sessions, services, models) into it, or refactoring the app breaks old migrations. `op` and `sqlalchemy` only.
- Never edit a migration that has already been applied anywhere: Alembic won't rerun it. Write a new one.
- Use generic types (`sa.Integer`, `sa.String(10)`, `sa.DateTime`), which is what autogenerate writes.
- Timestamps: `sa.DateTime(timezone=True)` (`timestamptz`). Plain `TIMESTAMP` forgets the time zone, so laptop (Madrid) and RDS (UTC) values silently disagree.
- If a column always has a value, say so: `nullable=False`.

**Stairway test**: `upgrade head -> downgrade base -> upgrade head`. No `assert` needed: a failing migration raises. A `downgrade()` that silently does nothing is caught by the *final* upgrade (`DuplicateTable`), which is why the third step exists.

**pytest fixtures**: a function decorated with `@pytest.fixture` that tests request by parameter name. Code before `yield` is setup, after `yield` is teardown (runs even if the test fails).

## Code map
| File | What it does | Why it exists / why this way |
|---|---|---|
| `docs/PLAN.md` | The project guide | Restart from any point without context |
| `CLAUDE.md` | Rules for Claude Code sessions | Tutor mode + learning protocol |
| `PROGRESS.md` | Session log | Where we are and the next step |
| `docs/journal/` | Learning trace per sprint | Decisions, concepts, code map, bugs, kept for later |
| `backend/pyproject.toml` | Project metadata, runtime deps, dev group, build backend, `[tool.alembic]` | Single source for deps and (soon) tool config |
| `backend/uv.lock` | Exact pinned versions of every dependency | Reproducible installs locally, in CI and in Docker |
| `backend/.python-version` | Pins Python 3.12 for uv | Everyone (and CI) runs the same interpreter |
| `backend/src/market_desk/api/main.py` | FastAPI `app` + `GET /health` (readiness, uses DB) | Entry point uvicorn serves; home of all routers later |
| `backend/tests/test_health.py` | Tests `/health` with DB up (real Postgres) and down (overridden engine) | Covers both branches; shows the dependency-override pattern |
| `backend/tests/test_config.py` | Env var beats default; `get_settings()` caches and `cache_clear()` resets it | My exercise; pins down config behaviour the whole app relies on |
| `.gitattributes` | Forces LF line endings for every clone | Linux-bound code must not get CRLF |
| `docker-compose.yml` | Local Postgres 16 + pgvector with volume and healthcheck | Same DB locally as in CI and (RDS) in AWS |
| `backend/src/market_desk/config.py` | `Settings` (env vars / `.env`) + cached `get_settings()` | One typed place for all config; secrets stay out of code |
| `backend/src/market_desk/db/engine.py` | Cached SQLAlchemy engine + `database_is_reachable()` | One connection pool per process; health logic testable on its own |
| `backend/src/market_desk/db/base.py` | `Base` (DeclarativeBase) with constraint naming convention | Parent of every model; predictable constraint names for migrations |
| `backend/src/market_desk/db/session.py` | Cached `sessionmaker` + `get_session()` request dependency | One unit of work per request, always closed |
| `backend/alembic.ini` | Alembic logging config only | Settings in `pyproject.toml`, URL from `config.py` |
| `backend/src/market_desk/db/migrations/env.py` | How Alembic connects: URL from settings, `Base.metadata` for autogenerate, online/offline modes, 3s connect timeout | Single source of truth for the DB URL |
| `backend/src/market_desk/db/migrations/script.py.mako` | Template for new migration files (modern type hints) | Generated files pass ruff from the start |
| `backend/src/market_desk/db/migrations/versions/` | The migration chain; first: `ce4e8980d9ca` (empty) | Versioned schema history |
| `backend/tests/test_session.py` | Drives `get_session()` like FastAPI: works, then closed | Proves the cleanup runs |
| `backend/tests/test_migrations.py` | Stairway test (up -> down -> up) | My exercise; catches broken `downgrade()` on the PR |

## Gotchas and bugs
| Symptom | Cause | Fix | Lesson |
|---|---|---|---|
| `StarletteDeprecationWarning: Using httpx with starlette.testclient is deprecated` | Recent Starlette moved its TestClient to the `httpx2` package | `uv remove --dev httpx && uv add --dev httpx2` | Read warnings: they tell you about upcoming breakage. `httpx` itself is still what we'll use for API clients in Sprint 1 |
| `uv`/`gh` "command not found" right after installing | The terminal was opened before the install changed PATH | Open a new terminal | PATH is read when a shell starts |
| "LF will be replaced by CRLF" warnings on `git add` | `core.autocrlf=true` (Git for Windows default) converts line endings in the working copy | `.gitattributes` with `* text=auto eol=lf` | Line endings are a repo setting, not a personal one |
| Health test fails with `ArgumentError: Could not parse SQLAlchemy URL` only when run after the config test | Config test went through `get_settings()` with a fake `DATABASE_URL`; the cached `Settings` outlived the test (`monkeypatch` restores env vars, not caches) | Build `Settings()` directly in that test; clear the cache at start and end of the caching test | Caches are shared state; check tests in more than one order |
| Every `docker` command returns `500 Internal Server Error ... dockerDesktopLinuxEngine` | Docker Desktop's engine crashed | Quit and reopen Docker Desktop, `docker compose up -d`; data survives in the volume | Tell "my code is broken" apart from "my tools are broken" |
| `alembic current` hangs for minutes | DB unreachable and `env.py`'s engine had no `connect_timeout` (the app's engine did) | `connect_args={"connect_timeout": 3}` in `env.py` | Every DB connection needs a timeout, including one-off tools |
| `CommandError: No 'script_location' key found` in a test | `Config("../alembic.ini")`: wrong relative path, a missing file silently gives an empty Config, and `script_location` lives in `pyproject.toml` anyway | Package notation `market_desk:db:migrations` | Same relative-path trap as `.env` |
| Stairway test fails with `DuplicateTable: relation "watchlist" already exists` even after fixing `downgrade()` | An earlier run with `downgrade()` = `pass` left `alembic_version` at base but the table in place | `DROP TABLE watchlist;` by hand | `alembic_version` and the real schema can drift; Alembic trusts the version table |
| (avoided) `.env` at repo root ignored when running from `backend/` | `env_file` paths are relative to the current directory | `env_file=("../.env", ".env")` | Relative paths resolve from where you *run*, not where the file lives |

## Exercises
| Date | Task (type) | Outcome | What I got wrong | Lesson |
|---|---|---|---|---|
| 2026-10-11 | Tasks 1-2. A: remove `dependency_overrides.clear()`, predict and run tests in reverse order (predict/verify). B: write `tests/test_config.py`, env var overrides default + `get_settings()` caching (write a missing test) | Done: 4 tests pass in every order | Didn't know `monkeypatch`; used `get_settings()` where a fresh `Settings()` was needed (order-dependent, then polluted the cache for the health test); used `==` to check "same object"; in A, blamed the fake URL instead of the leaked dependency override | Shared state (app overrides, caches, env) leaks between tests; test the object directly, not through the cache; `is` for identity |
| 2026-10-12 | Task 3. A: hand-written `watchlist` migration, predict constraint names, apply, inspect with `\d`, downgrade, delete. B: stairway test with Alembic's command API (write a missing test) | Done: names matched the convention; 6 tests pass; broken `downgrade()` caught by the final upgrade | Imported app code (`get_session`) into a migration; `TIMESTAMP` without time zone and nullable `created_at`; `Config("../alembic.ini")` relative path; used `command.current` as if it checked something | Migrations are frozen history (no app imports); `timestamptz`; `alembic_version` is the only thing Alembic trusts |

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
- [ ] Stairway test runs `downgrade base` on the **dev** DB: harmless now, wipes local data from Sprint 1. Options: separate `market_desk_test` database for pytest, or run that test only in CI. Decide before Sprint 1's first model.

## Retrospective (at sprint end)
