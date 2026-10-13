# Progress Log

Newest entry first. One entry per working session. The plan is in [`docs/PLAN.md`](docs/PLAN.md).

**Current sprint:** Sprint 0 — Scaffold (6 of 9 tasks done)
**Hours so far:** ~7.5 / ~89

<!-- Template (copy above the latest entry):
## YYYY-MM-DD · Sprint N · Xh
- **Done:** ...
- **Learned:** key concept(s); details in docs/journal/sprint-N.md
- **Next step:** the exact first thing to do next session
- **Blockers / notes:** ...
-->

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
