---
tags:
  - python-packaging
  - fastapi
---

# 1. Package and health endpoint

**Sprint 0** · **Date:** 2026-10-10 · **Plan item:** `backend/pyproject.toml` with uv; `src/market_desk/` package; FastAPI app with `/health`

## What and why
An installable Python package managed by uv, in a `src/` layout, with a FastAPI app exposing `GET /health`. It's the smallest thing that runs, gets tested and can be packaged, so every later piece has somewhere to live.

## Decisions
| Date | Decision | Why | Alternatives considered | ADR |
|---|---|---|---|---|
| 2026-10-10 | uv with `uv init --package` and a `src/` layout; Python pinned to 3.12 | One tool for Python version, venv, deps and lockfile; `--package` makes the code an installable package so tests import it like a user would | Poetry; pip + venv + requirements.txt; flat layout | — (in stack table) |
| 2026-10-10 | `pytest` + `httpx2` as a dev dependency group, not runtime deps | Test-only tools shouldn't ship in the production image; Starlette's TestClient now expects `httpx2` | Put them in `dependencies`; keep `httpx` and live with the deprecation warning | — |
| 2026-10-10 | App lives in `market_desk/api/main.py`, not the package root | Matches the repo layout in PLAN section 7: `api/` is one layer next to `clients/`, `agent/`, etc. | Single `main.py` at package root | — |
| 2026-10-10 | `.gitattributes` with `eol=lf` | Code runs on Linux (Docker, CI, AWS); CRLF breaks shell scripts and Makefiles; per-repo file beats each machine's `core.autocrlf` | Rely on everyone's git config | — |

## Concepts

### `pyproject.toml`
The one standard file (PEP 621) that describes a Python project. `[project]` holds metadata and *runtime* dependencies (what the app needs to run). `[dependency-groups]` holds *dev-only* groups (tests, linters) that never get installed in production. `[build-system]` says which tool turns the source into an installable package (here `uv_build`).

### `uv.lock`
The exact resolved version of every package, transitive ones included. `pyproject.toml` says `fastapi>=0.143.0` (a range); the lock says exactly which version. Commit it so CI, Docker and your laptop install identical environments. `uv sync` installs from it; `uv add` updates both files.

### `src/` layout
The package lives in `backend/src/market_desk/`, not `backend/market_desk/`. Python can't import it just because it's in the current folder; it has to be *installed* (uv installs it in editable mode into `.venv`). That way tests exercise the package the way a real user would, and a missing file or a broken package config fails in tests instead of in production.

### Why `src/` prevents "works on my machine"
Without `src/`, Python puts the current directory on `sys.path`, so `import market_desk` finds the loose source folder even if the package was never installed or is misconfigured. Tests pass locally and packaging bugs only appear where the package is really installed (Docker, CI). With `src/`, the only way the import works is through the installed package, so those bugs fail in tests first.

### `uv run` auto-syncs
Before running a command, `uv run` checks `.venv` against `uv.lock` and creates/updates it if needed. Deleting `.venv` is harmless: the next `uv run` rebuilds it identically.

### ASGI, uvicorn and FastAPI
FastAPI is a framework: it maps URLs to Python functions and validates input/output. It doesn't listen on a port itself. Uvicorn is the *ASGI server*: it opens the socket, speaks HTTP, and calls the app object. `uvicorn market_desk.api.main:app` means "import the module `market_desk.api.main`, take the variable `app`".

### Return type annotations in FastAPI
`-> dict[str, str]` isn't decoration. FastAPI uses it to validate the response and to document it in the OpenAPI schema (`/docs`, `/openapi.json`). In Sprint 4 that schema generates the frontend's TypeScript types.

### `TestClient`
Calls the app *in-process*: no server, no port, no network. It's fast and deterministic, and it's what lets CI test endpoints without starting uvicorn.

## Code map
| File | What it does | Why it exists / why this way |
|---|---|---|
| `backend/pyproject.toml` | Project metadata, runtime deps, dev group, build backend; later also all tool config | Single source for deps and tool config |
| `backend/uv.lock` | Exact pinned versions of every dependency | Reproducible installs locally, in CI and in Docker |
| `backend/.python-version` | Pins Python 3.12 for uv | Everyone (and CI) runs the same interpreter |
| `backend/src/market_desk/api/main.py` | FastAPI `app` + `GET /health` | Entry point uvicorn serves; home of all routers later |
| `.gitattributes` | Forces LF line endings for every clone | Linux-bound code must not get CRLF |

## Gotchas
!!! bug "`StarletteDeprecationWarning: Using httpx with starlette.testclient is deprecated`"
    **Cause:** recent Starlette moved its TestClient to the `httpx2` package.
    **Fix:** `uv remove --dev httpx && uv add --dev httpx2`.
    **Lesson:** read warnings: they tell you about upcoming breakage. `httpx` itself is still what we'll use for API clients in Sprint 1.

!!! bug "`uv` / `gh`: \"command not found\" right after installing"
    **Cause:** the terminal was opened before the install changed PATH.
    **Fix:** open a new terminal.
    **Lesson:** PATH is read when a shell starts.

!!! bug "\"LF will be replaced by CRLF\" warnings on `git add`"
    **Cause:** `core.autocrlf=true` (the Git for Windows default) converts line endings in the working copy.
    **Fix:** `.gitattributes` with `* text=auto eol=lf`.
    **Lesson:** line endings are a repo setting, not a personal one.

## Check questions
!!! note "Reconstructed"
    These questions were written during the journal migration, from what this task covered; the originals weren't recorded.

??? question "You delete `backend/.venv` and run `uv run pytest`. What happens?"
    uv sees there's no environment, creates `.venv`, installs exactly what `uv.lock` lists (plus the project itself, editable), then runs pytest. Nothing is lost: the lock is the source of truth, the venv is disposable.

??? question "With a flat layout (no `src/`), tests pass on your laptop but `import market_desk` fails in the Docker image. How is that possible?"
    Running from `backend/`, Python puts the current directory on `sys.path`, so the import finds the loose source folder without the package ever being installed. In the image only the *installed* package exists; if packaging is misconfigured (a missing file, a wrong package name), it fails there first. The `src/` layout makes tests go through the installed package, so the bug shows up locally.

??? question "Why are `pytest` and `httpx2` in a dependency group instead of `[project] dependencies`?"
    `dependencies` is what the app needs to *run*, and it all goes into the production image. Test tools are only needed to develop; keeping them in a group means the image (`uv sync --no-dev`) is smaller and has less attack surface.

??? question "FastAPI or uvicorn: which one opens port 8000?"
    Uvicorn. FastAPI is the app (routing, validation); uvicorn is the ASGI server that listens on the socket, parses HTTP and calls the app. That's also why `TestClient` can test the app with no server at all.

## Guided exercise
Tasks 1 and 2 shared one exercise (test isolation and a missing config test): see task 2's page.

## Explain it in 2 minutes
The backend is an installable Python package managed by uv: `pyproject.toml` declares what it needs, `uv.lock` pins every exact version, so my laptop, CI and Docker install the same thing. It uses a `src/` layout, which means Python can only import the code through the installed package, never by accident from the current folder, so packaging mistakes fail in tests rather than in the container. The app itself is FastAPI, served by uvicorn: FastAPI maps routes and validates data using the type hints, uvicorn is the server. The first endpoint is `/health`, tested in-process with `TestClient`. Dev tools like pytest live in a separate dependency group, so they never ship in the production image.
