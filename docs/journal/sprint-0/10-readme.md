---
tags:
  - docs
  - github
---

# 10. README

**Sprint 0** · **Date:** 2026-10-14 · **Plan item:** README: one-paragraph pitch + "Status: Sprint 0"

## What and why
The README is the repo's landing page: what the project is, where it stands, and how to run it, linking out for everything else. The pitch was already there; this task updated the status, linked the journal site, added CI and Docs badges and a quick start, and tested the quick start on a fresh clone.

## Decisions
| Date | Decision | Why | Alternatives considered | ADR |
|---|---|---|---|---|
| 2026-10-14 | README = pitch, status, badges, quick start, roadmap; everything else linked | The landing page answers "what, how far, how do I run it"; `PLAN.md` stays the single source for architecture and stack | Status line only (hides the site, no way to run it); a long README duplicating PLAN | — |
| 2026-10-14 | Badges pinned with `?branch=main` | States the intent explicitly; a PR's red run never shows on the README | No parameter (shows the default branch anyway, see the gotcha) | — |
| 2026-10-14 | Quick start tested on a fresh clone before merging | A quick start is only correct if it can be followed word for word | Trust that the commands work because they work here | — |

## Concepts

### The README as a landing page
Most visitors read the first screen and leave. It should answer three questions fast: what is this, what state is it in, how do I run it. Depth lives elsewhere (PLAN, ADRs, the journal) and is linked, not copied, so there's one place to keep up to date.

### Status badges
A badge is an SVG that GitHub Actions renders from a workflow's latest result (`.../actions/workflows/<file>/badge.svg`), wrapped in a link to that workflow's runs. Query parameters pick which runs count: `branch=`, `event=`. It's a live signal on the landing page that `main` is green.

### The fresh-clone test
Run the quick start in a brand-new clone, following only what the README says. Anything you have to guess, or that only works because your machine already has it, is a finding. It's the README's equivalent of the `src/` layout: test what someone else will actually get, not your working copy.

## Code map
| File | What it does | Why it exists / why this way |
|---|---|---|
| `README.md` | Pitch, CI/Docs badges, status, quick start, roadmap, disclaimer, license | The repo's landing page |

## Gotchas
!!! bug "I said the badge would show any branch's latest run without `?branch=main`"
    **Cause:** an outdated belief. GitHub's docs say a badge shows the **default branch** by default.
    **Fix:** kept `?branch=main` for clarity; corrected the explanation.
    **Lesson:** "it works" isn't the same as "it works for the reason I think". Check the docs when the reason matters.

!!! bug "Cleaning up the fresh clone removed `market-desk-api:latest`, the image the real repo uses"
    **Cause:** `docker-compose.yml` names the image explicitly (`image: market-desk-api`), so every copy of the repo builds and tags the same image; `docker compose down --rmi local` in the clone removed it.
    **Fix:** `make up` rebuilt it (from the build cache).
    **Lesson:** container, volume and network names are per project folder, but an explicit `image:` name is shared across all copies.

!!! bug "`make help | head -3` ends with `make: *** [Makefile:14: help] Error 3328`"
    **Cause:** `head` exits after 3 lines and closes the pipe; the next `echo` fails writing to it (broken pipe), so make reports the recipe as failed.
    **Fix:** nothing to fix: `make help` alone exits 0.
    **Lesson:** an error after `| head` is often the pipe, not the command.

## Check questions
??? question "A PR on a feature branch fails CI. Does the README's CI badge turn red?"
    No: the badge reflects `main` (`?branch=main`, and the default branch anyway). A PR's run doesn't count.

??? question "Why test the quick start on a fresh clone instead of in my working copy?"
    My copy already has `.venv`, `.env`, a built image and an installed hook, so a missing step can pass unnoticed. A fresh clone only has what's committed and what the README says.

## Guided exercise
**Task (type):** the fresh-clone test: `make down`, clone into a new folder, follow only the README's quick start, note anything guessed, clean up (verify).

**Outcome:** run by Claude on request (2026-10-14), in a scratchpad clone of `main` (`22c7209`): `cp .env.example .env`, `make install`, `make up`, `make check` (6 passed), `/health` `"database":"ok"`, `/docs` 200, `make docs-build` clean. One finding: the README didn't say how to get GNU make on Windows; added `winget install ezwinports.make`. Clone, its containers, volume and image removed; the real stack restarted.

**What I got wrong:** the check question on badges: predicted that removing `?branch=main` would turn the badge red on a failed PR; the badge shows the default branch either way (Claude's explanation was wrong first).

**Lesson:** follow the README literally on a clean machine; question the explanation, not only the result.

## Explain it in 2 minutes
The README is the landing page, so it answers three things quickly: what Market Desk is, where it stands, and how to run it. Two badges show whether CI and the docs build are green on `main`. The status line says Sprint 0 is done and links the session log and the learning journal site. The quick start is four commands (copy the env file, install, start the stack, run the checks), and I tested it on a fresh clone, following only the README; the one gap it found was how to install make on Windows. Everything deeper, architecture, stack, budget, decisions, is linked to `PLAN.md`, the ADRs and the journal instead of being copied, so there's only one place to keep up to date.
