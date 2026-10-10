# Sprint 0 — Scaffold

**Dates:** 2026-10-10 → · **Hours:** ~0.5h · **Plan:** [docs/PLAN.md, Sprint 0](../PLAN.md#sprint-0--scaffold-4h)

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

## Concepts
**`pyproject.toml`**: the one standard file (PEP 621) that describes a Python project. `[project]` holds metadata and *runtime* dependencies (what the app needs to run). `[dependency-groups]` holds *dev-only* groups (tests, linters) that never get installed in production. `[build-system]` says which tool turns the source into an installable package (here `uv_build`).

**`uv.lock`**: the exact resolved version of every package, transitive ones included. `pyproject.toml` says `fastapi>=0.143.0` (a range); the lock says exactly which version. Commit it so CI, Docker and your laptop install identical environments. `uv sync` installs from it; `uv add` updates both files.

**`src/` layout**: the package lives in `backend/src/market_desk/`, not `backend/market_desk/`. Python can't import it just because it's in the current folder; it has to be *installed* (uv installs it in editable mode into `.venv`). That way tests exercise the package the way a real user would, and a missing file or a broken package config fails in tests instead of in production.

**`uv run` auto-syncs**: before running a command, `uv run` checks `.venv` against `uv.lock` and creates/updates it if needed. Deleting `.venv` is harmless: the next `uv run` rebuilds it identically.

**Why `src/` prevents "works on my machine"**: without `src/`, Python puts the current directory on `sys.path`, so `import market_desk` finds the loose source folder even if the package was never installed or is misconfigured. Tests pass locally and packaging bugs only appear where the package is really installed (Docker, CI). With `src/`, the only way the import works is through the installed package, so those bugs fail in tests first.

**ASGI / uvicorn / FastAPI**: FastAPI is a framework: it maps URLs to Python functions and validates input/output. It doesn't listen on a port itself. Uvicorn is the *ASGI server*: it opens the socket, speaks HTTP, and calls the app object. `uvicorn market_desk.api.main:app` means "import the module `market_desk.api.main`, take the variable `app`".

**Return type annotations in FastAPI**: `-> dict[str, str]` isn't decoration. FastAPI uses it to validate the response and to document it in the OpenAPI schema (`/docs`, `/openapi.json`). In Sprint 4 that schema generates the frontend's TypeScript types.

**`TestClient`**: calls the app *in-process*: no server, no port, no network. It's fast and deterministic, and it's what lets CI test endpoints without starting uvicorn.

**Liveness vs readiness**: a liveness check answers "is the process alive?"; a readiness check answers "can it actually serve requests (DB reachable, etc.)?". `/health` is liveness only for now; task 2 adds the DB check.

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
| `backend/src/market_desk/api/main.py` | FastAPI `app` + `GET /health` | Entry point uvicorn serves; home of all routers later |
| `backend/tests/test_health.py` | In-process test of `/health` | First test; template for endpoint tests |

## Gotchas and bugs
| Symptom | Cause | Fix | Lesson |
|---|---|---|---|
| `StarletteDeprecationWarning: Using httpx with starlette.testclient is deprecated` | Recent Starlette moved its TestClient to the `httpx2` package | `uv remove --dev httpx && uv add --dev httpx2` | Read warnings: they tell you about upcoming breakage. `httpx` itself is still what we'll use for API clients in Sprint 1 |
| `uv`/`gh` "command not found" right after installing | The terminal was opened before the install changed PATH | Open a new terminal | PATH is read when a shell starts |

## Commands and snippets worth keeping
```bash
cd backend
uv sync                                              # create .venv from uv.lock
uv add <pkg> / uv add --dev <pkg>                    # add runtime / dev dependency
uv run pytest -q                                     # run tests inside the venv
uv run uvicorn market_desk.api.main:app --reload     # dev server on :8000, docs at /docs
```

## Open questions
- [ ] ...

## Retrospective (at sprint end)
