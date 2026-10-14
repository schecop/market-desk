---
tags:
  - tooling
---

# 6. Makefile

**Sprint 0** · **Date:** 2026-10-13 → 2026-10-14 · **Plan item:** `Makefile`: `up`, `down`, `test`, `lint`, `fmt`

## What and why
One short name for every everyday command (`make up`, `make test`, `make lint`, `make check`), and CI calls the same targets, so local checks and CI checks can't drift apart.

## Decisions
| Date | Decision | Why | Alternatives considered | ADR |
|---|---|---|---|---|
| 2026-10-13 | `Makefile` as the single entry point; GNU make installed with `winget install ezwinports.make` | CI calls `make lint`/`make test`, so local and CI checks can't drift; `make` is on every Linux runner | `just`; `poe`/`tox`; PowerShell scripts (Windows-only); `mingw32-make` (different name); msys64 on PATH (shadows Windows tools) | — |
| 2026-10-13 | `lint` only checks, `fmt` rewrites | CI must fail on bad formatting, not fix it in a throwaway runner | One target that formats and checks | — |

## Concepts

### Make essentials
A target is assumed to be a **file** to build; `.PHONY` marks it as a command name, otherwise a file or folder called `test` makes `make test` print "up to date" and silently run nothing. `target: a b` = **prerequisites**: `a` then `b` run first (left to right normally; possibly in parallel with `make -j`), then the target's own recipe. Each recipe line runs in a **new shell** (a `cd` doesn't carry over: write `cd backend && ...`), and make stops at the first failing line. Recipe lines must start with a **tab**. If a Makefile must call itself, use `$(MAKE)`, not `make`, so the name and flags (`-n`, `-j`) carry over.

## Code map
| File | What it does | Why it exists / why this way |
|---|---|---|
| `Makefile` | `help`, `install`, `up`, `down`, `dev`, `test`, `lint`, `fmt`, `check` | One name per everyday command; CI calls the same targets |

## Check questions
!!! note "Reconstructed"
    These questions were written during the journal migration, from what this task covered; the originals weren't recorded.

??? question "You create a folder called `test/` at the repo root and remove `test` from `.PHONY`. What does `make test` do?"
    It prints that `test` is up to date and runs nothing: make treats a target as a file, sees `test/` exists and has no prerequisites newer than it, so there's nothing to build. `.PHONY` says "this is a command name, always run it".

??? question "A recipe has `cd backend` on one line and `uv run pytest` on the next. Where does pytest run?"
    In the repo root, not `backend/`: each recipe line runs in a new shell, so the `cd` is lost. Hence `cd backend && uv run pytest` on one line.

??? question "Why does `lint` only check, with formatting in a separate `fmt` target?"
    CI runs `lint`. If it reformatted, it would "fix" the code in a throwaway runner and pass, while the badly formatted code stays in the repo. A check must fail, so the fix happens where it can be committed.

## Guided exercise
Shared with task 7 (add `make check`; break CI on purpose): see [task 7's page](07-ci.md#guided-exercise).

## Explain it in 2 minutes
The Makefile is the project's menu of commands: `make up` starts the stack, `make test` runs the tests, `make lint` checks without changing anything, `make fmt` fixes formatting, and `make check` is lint then tests, exactly what CI runs. CI calls these same targets instead of repeating raw commands in YAML, so there's one definition of "the checks". The make details that matter: targets are files unless marked `.PHONY`, each recipe line is a fresh shell, and prerequisites run before the target, which is how `check: lint test` works with no recipe of its own.
