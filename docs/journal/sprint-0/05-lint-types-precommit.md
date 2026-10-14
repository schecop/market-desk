---
tags:
  - code-quality
  - testing
---

# 5. Lint, types, test config and pre-commit

**Sprint 0** · **Date:** 2026-10-13 · **Plan item:** ruff + mypy + pytest configured in `pyproject.toml`; pre-commit hooks

## What and why
ruff for lint and formatting, mypy in strict mode, pytest with warnings as errors, all configured in `pyproject.toml`, and pre-commit hooks that run them before each commit. The checks are cheapest to turn on while the codebase is tiny.

## Decisions
| Date | Decision | Why | Alternatives considered | ADR |
|---|---|---|---|---|
| 2026-10-13 | ruff for lint + format (rules E, W, F, I, UP, B, SIM; line length 100) | One fast tool replaces black, isort, flake8 and plugins | black + isort + flake8 | — |
| 2026-10-13 | mypy `strict = true` from day one, with the Pydantic plugin | Cheapest while the codebase is tiny; enabling later means hundreds of errors at once | Non-strict mypy; pyright | — |
| 2026-10-13 | pytest `filterwarnings = ["error"]` | Deprecations fail the run instead of scrolling past (the `httpx` warning in task 1 would have been caught) | Default: warnings only printed | — |
| 2026-10-13 | pre-commit Python hooks as `repo: local` via `uv run --directory backend` | Same ruff/mypy versions as `uv.lock`; mypy sees the real dependencies | `ruff-pre-commit` / `mirrors-mypy` repos (second version to sync; isolated mypy reports false errors) | — |
| 2026-10-13 | pytest not in pre-commit | Needs Postgres and takes seconds; runs in `make test` and CI | Run tests on every commit | — |
| 2026-10-13 | Unused imports allowed only in `migrations/versions/` + Alembic post-write hooks run ruff on new migrations | Template always imports `sa`/`op`; generated files still pass every other check | Edit the template per migration; ignore migrations entirely | — |

## Concepts

### Linter vs formatter vs type checker
A *linter* (`ruff check`) finds likely bugs and bad patterns (unused imports, mutable default args); a *formatter* (`ruff format`) rewrites layout so style is never discussed; a *type checker* (`mypy`) proves the annotations are consistent across every code path. None of them run the code.

### What mypy strict catches, and what it can't
Tests check the inputs you thought of; mypy checks every path for every type. The planted bug `return conn.execute(...).scalar()` in a `-> bool` function passed all 6 tests (`1` is truthy) but failed mypy with `[no-any-return]`; a query returning `0`/`NULL` would have made `/health` say 503 for a healthy DB. Don't trust mypy's "Success" past `Any` (untyped libraries, `# type: ignore`, `cast`), for logic errors (a wrong `bool` is still a `bool`), or for runtime data (JSON, env, DB rows): that's Pydantic's job.

### pre-commit
A framework that installs a git hook (`.git/hooks/pre-commit`) running configured checks on `git commit`. A hook that *modifies* files counts as failed on purpose: the fix isn't staged yet, so you review it and `git add` again. `.git/hooks` isn't versioned: every clone runs `pre-commit install` once. Hooks can be skipped (`--no-verify`), so CI runs the same checks again in a clean environment from the lockfile, plus the tests.

### pytest config
`filterwarnings = ["error"]` turns warnings into failures; `--strict-markers` makes a misspelled marker an error; `-ra` prints a summary of skips/failures.

## Code map
| File | What it does | Why it exists / why this way |
|---|---|---|
| `backend/pyproject.toml` | `[tool.ruff]`, `[tool.mypy]`, `[tool.pytest.ini_options]` | All tool config in one file |
| `.pre-commit-config.yaml` | Hooks on `git commit`: hygiene checks, ruff check/format, mypy (via `uv run`) | Problems blocked before a commit exists |

## Gotchas
!!! bug "(exercise) 6 tests green, mypy `Returning Any from function declared to return \"bool\" [no-any-return]`"
    **Cause:** `.scalar()` returns `Any`; `/health` only checks truthiness, and `1` is truthy.
    **Fix:** return `True` after a successful query (or `scalar_one() == 1`).
    **Lesson:** tests see the inputs you tried; types cover every path.

## Check questions
!!! note "Reconstructed"
    These questions were written during the journal migration, from what this task covered; the originals weren't recorded.

??? question "You run `git commit` and the ruff-format hook fails, but the file is already reformatted on disk. Why did it fail, and what do you do?"
    A hook that changes files fails on purpose: the fix is in the working copy but not in the commit you were making. Review the change, `git add` it, and commit again.

??? question "All tests pass and mypy reports `Success`. Name one kind of bug that can still be there."
    A logic error with the right type (a `bool` that's wrong is still a `bool`); anything hidden behind `Any` (untyped libraries, `cast`, `# type: ignore`); bad runtime data (JSON, env vars, DB rows), which only Pydantic validation catches.

??? question "Why run pre-commit's ruff and mypy through `uv run` (`repo: local`) instead of the official hook repos?"
    The official repos install their own copy of each tool, so there are two versions to keep in sync, and isolated mypy can't see the project's dependencies, which gives false errors. `uv run` uses exactly what `uv.lock` pins.

## Guided exercise
**Task (type):** A: find and fix a planted bug from mypy's output (fix a bug). B: commit a badly formatted file and watch pre-commit block it (break on purpose).

**Outcome:** done (2026-10-13): mypy clean, 6 passed; commit blocked, ruff fixed the file.

**What I got wrong:** explained the bug as "no False returned"; the core issue is `Any` where `bool` is promised, and falsy-but-valid results (`0`/`NULL`) giving a false 503.

**Lesson:** green tests ≠ correct types; modifying hooks fail on purpose so you review the fix.

## Explain it in 2 minutes
Three automatic checks, each catching a different kind of problem: ruff lints for likely bugs and formats the code so style is never discussed, mypy in strict mode checks types on every code path, and pytest treats warnings as errors so deprecations get fixed instead of ignored. They're configured in `pyproject.toml` and run on every commit through pre-commit, using the same versions as the lockfile. Strict typing paid off right away: a planted bug passed all the tests but mypy caught it. Hooks can be skipped, though, and only see what's being committed, so CI runs the same checks again on the whole repo.
