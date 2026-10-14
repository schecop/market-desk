# Sprint 0 — Scaffold

**Dates:** 2026-10-10 → · **Hours:** ~7.5h · **Plan:** [PLAN.md, Sprint 0](../../PLAN.md#sprint-0-scaffold-65h)

## Goal (in my own words)
A clean, professional skeleton every later sprint builds on: an installable Python package, a FastAPI service backed by Postgres in Docker, automated lint/type/test checks, and CI on every PR. Everything later depends on it.

## Tasks
| # | Task | Page |
|---|---|---|
| 1 | uv package, `src/` layout, FastAPI `/health` | [Package and health](01-package-and-health.md) |
| 2 | Postgres + pgvector in Compose; `/health` checks the DB | [Postgres and readiness](02-postgres-and-readiness.md) |
| 3 | SQLAlchemy session + Alembic | [SQLAlchemy and Alembic](03-sqlalchemy-and-alembic.md) |
| 4 | Multi-stage Dockerfile + `migrate` / `api` services | [Dockerfile](04-dockerfile.md) |
| 5 | ruff, mypy strict, pytest config, pre-commit | [Lint, types, pre-commit](05-lint-types-precommit.md) |
| 6 | Makefile | [Makefile](06-makefile.md) |
| 7 | GitHub Actions CI | [CI](07-ci.md) |
| 8 | Journal site (MkDocs Material, GitHub Pages) | [Journal site](08-journal-site.md) |
| 9 | Branch protection on `main` | — |
| 10 | README pitch + status | — |

## Sprint-level decisions
| Date | Decision | Why | Alternatives considered | ADR |
|---|---|---|---|---|
| 2026-10-10 | Standalone public repo outside OneDrive (`C:\Users\pablo\PP\market-desk`) | OneDrive syncing `.venv`, `node_modules` and Docker volumes causes slowness and file locks; GitHub is the backup | Inside an existing workspace folder; OneDrive folder | — |
| 2026-10-10 | Learning protocol in `CLAUDE.md` (explain before acting, walk through after, journal everything) | This is a learning project: understanding and a re-readable trace matter more than speed | Let Claude generate freely and review at the end | — |
| 2026-10-14 | First PR as a draft into `main` covering tasks 1-7; journal site, branch protection and README in later PRs | Draft runs CI but signals "not ready"; one reviewable unit for the scaffold | One PR per task (would have needed to start on day 1) | — |

## Project files
Files that belong to the project rather than to one task.

| File | What it does | Why it exists / why this way |
|---|---|---|
| `docs/PLAN.md` | The project guide | Restart from any point without context |
| `CLAUDE.md` | Rules for Claude Code sessions | Tutor mode + learning protocol |
| `PROGRESS.md` | Session log | Where we are and the next step |
| `docs/journal/` | Learning trace: one folder per sprint, one page per task | Decisions, concepts, code map, bugs, kept for later |

## Explain it in 2 minutes
**Why a `src/` layout?** The code lives in `backend/src/market_desk/`, so Python can't import it just because I'm standing in the right folder: it has to be installed as a package, which uv does in editable mode. That means the tests import the code exactly the way the Docker image does. If packaging is broken, a file missing from the package, a wrong name, the tests fail on my laptop instead of the container failing on AWS.

**What runs in CI, and why?** Every PR and every push to `main` runs two GitHub Actions jobs in parallel. One starts a throwaway Postgres and runs `make lint` and `make test`: ruff, mypy in strict mode, and pytest with warnings as errors, against a real database. The other builds the Docker image, so a broken Dockerfile shows up on the PR too. They're the same `make` targets I run locally, so "passing" has one definition. A third workflow builds this journal in strict mode, so a broken link fails the PR, and deploys it to GitHub Pages when `main` changes. CI is the real gate because pre-commit hooks only see what's being committed and can be skipped; CI checks the whole repo in a clean environment built from the lockfile.

**How do you keep a solo repo disciplined?** I treat it like a team repo with one member. Work happens on branches and goes to `main` through PRs with green CI, never straight pushes. Commits follow conventional commits and explain *why*. Decisions with real alternatives get recorded, and the lasting ones get an ADR. Tool versions are pinned (`uv.lock`, exact action tags), so a build from months ago can be reproduced. The next step is branch protection (task 9): GitHub itself refuses a merge to `main` without a PR and green checks, so discipline stops depending on me remembering.

??? question "The Docs check uses a path filter. What goes wrong if branch protection makes it a *required* check?"
    A PR that doesn't touch any of its paths never runs it, so the required check never reports and the PR waits forever as "Expected — waiting for status". Either don't require path-filtered checks, or make the workflow always run and decide inside a job whether there's anything to do.

## Open questions
- [ ] Stairway test runs `downgrade base` on the **dev** DB: harmless now, wipes local data from Sprint 1. Options: separate `market_desk_test` database for pytest, or run that test only in CI. Decide before Sprint 1's first model.

## Retrospective (at sprint end)
