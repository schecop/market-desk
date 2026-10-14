---
tags:
  - postgres
  - migrations
  - testing
---

# 3. SQLAlchemy sessions and Alembic

**Sprint 0** · **Date:** 2026-10-11 → 2026-10-12 · **Plan item:** SQLAlchemy session + Alembic initialised (first empty migration)

## What and why
A per-request SQLAlchemy session, a `Base` class with a constraint naming convention, and Alembic wired into the package with a first, empty migration. The schema gets a version history from day one, and a stairway test proves every migration can go up and down.

## Decisions
| Date | Decision | Why | Alternatives considered | ADR |
|---|---|---|---|---|
| 2026-10-11 | Alembic config in `pyproject.toml` (`pyproject` template); `alembic.ini` keeps only logging | All tool config in one file; no DB URL in a committed file | `generic` template with everything in `alembic.ini` | — |
| 2026-10-11 | Migrations inside the package (`src/market_desk/db/migrations/`) | Matches PLAN layout; shipped with the code into the Docker image | `backend/alembic/` next to `src/` | — |
| 2026-10-11 | `env.py` reads the URL from `get_settings()` | App and migrations can never target different DBs; no credentials in `alembic.ini` | `sqlalchemy.url` in `alembic.ini`; separate env var for Alembic | — |
| 2026-10-11 | Constraint naming convention on `Base.metadata` | Predictable names (`pk_x`, `uq_x_col`) so later migrations can alter/drop constraints | Let Postgres generate names | — |
| 2026-10-11 | First migration empty; pgvector extension deferred to Sprint 3 | Learn the mechanism first; enable things when they're used | `CREATE EXTENSION vector` in the first migration | — |
| 2026-10-12 | Stairway test uses `Config("")` + `script_location="market_desk:db:migrations"` (package notation) | Works from any working directory, via the installed package | `Config(toml_file="pyproject.toml")`: reuses real config but path is relative to cwd | — |

## Concepts

### Session (unit of work)
A SQLAlchemy `Session` tracks the objects you load, add and change, and writes them all in one transaction on `commit()` (or throws them away on `rollback()`/close). `sessionmaker` is the factory; `get_session()` gives each request its own session and always closes it. `expire_on_commit=False` keeps objects usable after commit (no surprise reload, no error once the session is closed).

### Generator dependencies
A FastAPI dependency with `yield` runs up to `yield`, hands the value to the route, then resumes after the response: the code after `yield` (or the `with` exit) is the cleanup. Same shape as a pytest fixture. You can drive one by hand: `next(gen)` = setup, exhaust it = teardown.

### pytest fixtures
A function decorated with `@pytest.fixture` that tests request by parameter name. Code before `yield` is setup, after `yield` is teardown (runs even if the test fails).

### `DeclarativeBase` and metadata
Every model class inherits from `Base`; `Base.metadata` is the registry of all tables. Alembic's `--autogenerate` diffs that registry against the real DB, so models must be imported in `env.py` or autogenerate thinks they don't exist.

### Naming conventions
Constraints (primary key, unique, foreign key, index, check) have names in Postgres. Migrations refer to them by name (`op.drop_constraint("uq_watchlist_ticker", ...)`), so names must be predictable. `MetaData(naming_convention=...)` makes SQLAlchemy name them; Alembic's `op.create_table` uses the same convention, as `\d watchlist` showed (`pk_watchlist`, `uq_watchlist_ticker`).

### Migrations (Alembic)
The version history of the schema. Each file has `revision`, `down_revision` (its parent, which forms a chain), `upgrade()` and `downgrade()`. The DB stores **one row** in `alembic_version`: the revision it's at. Alembic compares that with the chain to decide what to run, and **never looks at the real tables**. If they disagree (manual changes, a broken `downgrade()`), later migrations crash. Postgres runs DDL inside transactions, so a failing migration rolls back cleanly. Commands: `upgrade head`, `downgrade -1`, `downgrade base`, `current`, `history`, `revision -m`, `revision --autogenerate` (always review its output).

### Migration rules of thumb
- A migration is frozen history: never import app code (sessions, services, models) into it, or refactoring the app breaks old migrations. `op` and `sqlalchemy` only.
- Never edit a migration that has already been applied anywhere: Alembic won't rerun it. Write a new one.
- Use generic types (`sa.Integer`, `sa.String(10)`, `sa.DateTime`), which is what autogenerate writes.
- Timestamps: `sa.DateTime(timezone=True)` (`timestamptz`). Plain `TIMESTAMP` forgets the time zone, so laptop (Madrid) and RDS (UTC) values silently disagree.
- If a column always has a value, say so: `nullable=False`.

### Stairway test
`upgrade head -> downgrade base -> upgrade head`. No `assert` needed: a failing migration raises. A `downgrade()` that silently does nothing is caught by the *final* upgrade (`DuplicateTable`), which is why the third step exists.

## Code map
| File | What it does | Why it exists / why this way |
|---|---|---|
| `backend/pyproject.toml` | `[tool.alembic]`: `script_location` in package notation, date-prefixed file names, ruff post-write hooks | All tool config in one file |
| `backend/src/market_desk/db/base.py` | `Base` (DeclarativeBase) with constraint naming convention | Parent of every model; predictable constraint names for migrations |
| `backend/src/market_desk/db/session.py` | Cached `sessionmaker` + `get_session()` request dependency | One unit of work per request, always closed |
| `backend/alembic.ini` | Alembic logging config only | Settings in `pyproject.toml`, URL from `config.py` |
| `backend/src/market_desk/db/migrations/env.py` | How Alembic connects: URL from settings, `Base.metadata` for autogenerate, online/offline modes, 3s connect timeout | Single source of truth for the DB URL |
| `backend/src/market_desk/db/migrations/script.py.mako` | Template for new migration files (modern type hints) | Generated files pass ruff from the start |
| `backend/src/market_desk/db/migrations/versions/` | The migration chain; first: `ce4e8980d9ca` (empty) | Versioned schema history |
| `backend/tests/test_session.py` | Drives `get_session()` like FastAPI: works, then closed | Proves the cleanup runs |
| `backend/tests/test_migrations.py` | Stairway test (up -> down -> up) | My exercise; catches broken `downgrade()` on the PR |

## Gotchas
!!! bug "`alembic current` hangs for minutes"
    **Cause:** DB unreachable and `env.py`'s engine had no `connect_timeout` (the app's engine did).
    **Fix:** `connect_args={"connect_timeout": 3}` in `env.py`.
    **Lesson:** every DB connection needs a timeout, including one-off tools.

!!! bug "`CommandError: No 'script_location' key found` in a test"
    **Cause:** `Config("../alembic.ini")`: wrong relative path, a missing file silently gives an empty Config, and `script_location` lives in `pyproject.toml` anyway.
    **Fix:** package notation `market_desk:db:migrations`.
    **Lesson:** same relative-path trap as `.env`.

!!! bug "Stairway test fails with `DuplicateTable: relation \"watchlist\" already exists` even after fixing `downgrade()`"
    **Cause:** an earlier run with `downgrade()` = `pass` left `alembic_version` at base but the table in place.
    **Fix:** `DROP TABLE watchlist;` by hand.
    **Lesson:** `alembic_version` and the real schema can drift; Alembic trusts the version table.

## Check questions
!!! note "Reconstructed"
    These questions were written during the journal migration, from what this task covered; the originals weren't recorded.

??? question "Someone drops a table by hand in psql. What does Alembic think the schema is now?"
    Exactly what it thought before: it only reads the one row in `alembic_version` and never inspects the real tables. The next migration that touches that table crashes. Schema changes go through migrations, never by hand.

??? question "Why does the stairway test end with a second `upgrade head`? Wouldn't up → down be enough?"
    A `downgrade()` that does nothing (`pass`) runs without error, so up → down passes. The final upgrade tries to create the tables again and fails with `DuplicateTable`, which is what exposes the broken downgrade.

??? question "A migration needs a list of tickers. Why not `from market_desk.services import load_tickers` inside it?"
    Migrations are frozen history; app code keeps changing. When `load_tickers` is renamed or changed months later, the old migration breaks, and so does every fresh database built from the chain. Use only `op` and `sqlalchemy`, with the data inlined.

??? question "Why give constraints predictable names with a naming convention?"
    Later migrations refer to constraints by name (`op.drop_constraint("uq_watchlist_ticker", ...)`). Names Postgres generates aren't known in advance, so you couldn't write that migration reliably.

## Guided exercise
**Task (type):** A: a hand-written `watchlist` migration: predict the constraint names, apply, inspect with `\d`, downgrade, delete. B: a stairway test with Alembic's command API (write a missing test).

**Outcome:** done (2026-10-12): names matched the convention; 6 tests pass; a broken `downgrade()` is caught by the final upgrade.

**What I got wrong:** imported app code (`get_session`) into a migration; `TIMESTAMP` without time zone and nullable `created_at`; `Config("../alembic.ini")` relative path; used `command.current` as if it checked something.

**Lesson:** migrations are frozen history (no app imports); `timestamptz`; `alembic_version` is the only thing Alembic trusts.

## Explain it in 2 minutes
Each request gets its own SQLAlchemy session, a unit of work that's always closed, through a FastAPI dependency with `yield`. All models inherit from one `Base` whose metadata has a naming convention, so every constraint has a predictable name that later migrations can refer to. Alembic keeps the schema's version history: each migration points at its parent, and the database stores a single row saying which revision it's at. Alembic trusts that row, never the real tables, so schema changes only ever go through migrations. Its config lives in `pyproject.toml`, and `env.py` takes the URL from the same settings as the app, so they can't point at different databases. A stairway test runs up, down, up on every PR, which catches a broken downgrade before it reaches anyone.
