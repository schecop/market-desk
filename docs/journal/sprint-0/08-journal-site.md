---
tags:
  - docs
  - ci
---

# 8. Journal site

**Sprint 0** · **Date:** 2026-10-12 → 2026-10-14 · **Plan item:** Journal site: MkDocs Material on GitHub Pages, one page per task, deployed by a GitHub Actions workflow on push to `main` ([ADR-0002](../../adr/0002-journal-site-mkdocs-github-pages.md))

## What and why
The journal becomes a searchable static site built from the same Markdown in `docs/`: one page per task, check questions with hidden answers for self-testing, review pages across sprints. It's built with MkDocs Material and will be deployed to GitHub Pages by a workflow.

## Decisions
| Date | Decision | Why | Alternatives considered | ADR |
|---|---|---|---|---|
| 2026-10-12 | Journal published as a site: MkDocs Material on GitHub Pages, one page per task; new Sprint 0 task right after CI | Searchable, visual journal for review; same Markdown as the *Record* step, so nothing to keep in sync; free | Plain Markdown on GitHub; a separate page outside the repo | [ADR-0002](../../adr/0002-journal-site-mkdocs-github-pages.md) |
| 2026-10-14 | `mkdocs-material` in a `docs` dependency group in `backend/pyproject.toml`; `make docs-serve` / `make docs-build` | Locked in `uv.lock` like everything else; a non-default group, so neither the Docker image nor the CI test job installs it | `uvx mkdocs-material` (no lockfile: versions drift); a second Python project for docs | — |
| 2026-10-14 | Pin `mkdocs>=1.6,<2` | MkDocs 2.0 removes the plugin and theme systems Material needs, with no migration path | Leave it unpinned and find out on an upgrade | [ADR-0002](../../adr/0002-journal-site-mkdocs-github-pages.md) (consequences) |
| 2026-10-14 | `docs_dir: docs`: the site renders the existing Markdown; explicit `nav` | One source of truth; sidebar order chosen, not alphabetical | A separate site folder; automatic nav | — |
| 2026-10-14 | `--strict` builds + `validation.links.anchors: warn` | Broken links, missing pages and broken `#anchors` fail the build instead of reaching the site | Default (warnings printed, anchors only INFO) | — |
| 2026-10-14 | Links follow MkDocs anchors (`#sprint-0-scaffold-65h`), not GitHub's (`#sprint-0--scaffold-65h`) | The site is the main reader, and only the strict build can check anchors | Keep GitHub anchors (broken on the site, unchecked) | — |
| 2026-10-14 | Review pages are link lists into the task pages, not copies | One source; the strict build checks every link | `pymdownx.snippets` includes (no duplication, but marker comments everywhere) | — |
| 2026-10-14 | Separate `docs.yml` workflow: strict build on PRs, deploy with `actions/deploy-pages` on `main` only | Its own path filters; only the deploy job gets write permissions, so CI's token stays read-only; no generated branch | A job in `ci.yml`; `mkdocs gh-deploy` to a `gh-pages` branch (`contents: write`, generated commits in history) | — |
| 2026-10-14 | `check-yaml` hook excludes `mkdocs.yml` | Its `!!python/name:` tag fails the safe loader; `make docs-build` validates the file instead | `--unsafe` (syntax-only check for every YAML file) | — |
| 2026-10-14 | Check questions for tasks 1-7 reconstructed during the migration, and labelled so | The originals weren't recorded; questions from what was actually hit are still useful for review | No questions for the old tasks | — |

## Concepts

### Static site generator
A tool that turns source files (here Markdown plus `mkdocs.yml`) into plain HTML, CSS and JS once, at build time. The result (`site/`) is just files: any static host can serve it, there's no server code and nothing to keep running. It's a build output, so it's gitignored and regenerated, like a Docker image.

### Docs as code
Documentation lives in the repo, next to the code it describes, in plain text: it's versioned, reviewed in PRs and checked in CI like code. The site is only a view of it.

### Strict builds as a link checker
By default MkDocs prints warnings (a broken link, a nav entry for a missing file) and builds anyway. `--strict` turns every warning into a failed build, so CI can stop a broken page. Some checks are only INFO by default (broken `#anchors`), so `validation:` raises them to warnings first.

### Heading anchors differ between renderers
Each Markdown renderer turns a heading into an id (a *slug*) with its own rules. For "Sprint 0 — Scaffold (~6.5h)", GitHub gives `sprint-0--scaffold-65h` (the `—` leaves two hyphens) and MkDocs gives `sprint-0-scaffold-65h`. A link written for one breaks on the other.

### Live reload
`mkdocs serve` watches the source files (with the `watchdog` package), rebuilds when one is saved, and tells the open browser tab to refresh. The edit-and-see loop takes about a second.

### Pages deployment with OIDC
`actions/deploy-pages` doesn't push anything to the repo. The job asks GitHub for a short-lived **OIDC token** (`id-token: write`), a signed statement of "this is workflow X in repo Y on ref Z", and Pages accepts the upload because of it. `pages: write` lets the job publish and nothing more. Compare `mkdocs gh-deploy`, which needs a token that can write the whole repo.

### Job-level permissions and conditions
`permissions:` at the top of a workflow is the default for every job; a job's own `permissions:` **replaces** it for that job (it doesn't add to it). `needs: build` waits for another job to succeed; `if: github.ref == 'refs/heads/main'` skips the job on PRs, so they build but never deploy.

### Path filters
`on: pull_request: paths:` runs the workflow only when a matching file changes. A code-only PR doesn't rebuild the site. The catch: a check that's *required* by branch protection but filtered out never reports, and the PR waits forever (relevant for task 9).

### Non-default dependency groups
`uv sync` installs the `dev` group by default and skips other groups. `uv run --group docs ...` adds the `docs` group for that command. Tools only needed for one job stay out of every other environment.

## Code map
| File | What it does | Why it exists / why this way |
|---|---|---|
| `mkdocs.yml` | Site config: `docs_dir`, nav, theme (light/dark), plugins (search, tags), Markdown extensions (admonitions, collapsible blocks, Mermaid, task lists), strict anchor validation | How the existing Markdown is rendered; the content stays in `docs/` |
| `docs/index.md` | Site home page | Landing page for the site root |
| `docs/journal/README.md` | Journal landing page: how pages are organised and added | Rewritten for one page per task |
| `docs/journal/_template-sprint.md` | Template for a sprint overview | Renamed from `_template.md` |
| `docs/journal/_template-task.md` | Template for a task page | One shape for every task page |
| `docs/journal/sprint-0/` | Sprint overview + one page per task | Replaces the single `sprint-0.md` |
| `docs/journal/review/` | Cross-sprint concepts, gotchas, commands and tags | Review without opening every task |
| `Makefile` | `docs-serve` (:8001, live reload) and `docs-build` (strict) | Same commands locally and in CI |
| `.gitignore` | Ignores `site/` | Build output, never committed |
| `.github/workflows/docs.yml` | Strict build on PRs (path-filtered); deploy to Pages on `main` with OIDC; manual trigger | Broken docs fail the PR; the site updates itself on merge |
| `.pre-commit-config.yaml` | `check-yaml` now excludes `mkdocs.yml` | Safe loader can't read its `!!python/name:` tag |

## Gotchas
!!! bug "First strict build fails: `Doc file 'PLAN.md' contains a link '../PROGRESS.md', but the target is not found`"
    **Cause:** `PROGRESS.md` is at the repo root, outside `docs_dir`, so it isn't part of the site.
    **Fix:** link to the file on GitHub with an absolute URL.
    **Lesson:** the site only contains `docs/`; links leaving it must be absolute.

!!! bug "A broken `#anchor` link passes `--strict`"
    **Cause:** MkDocs reports a missing anchor as INFO, not a warning, and `--strict` only fails on warnings.
    **Fix:** `validation: links: anchors: warn` in `mkdocs.yml`.
    **Lesson:** check what level a validation runs at before trusting a strict build.

!!! bug "The build prints a long warning from the Material team about MkDocs 2.0"
    **Cause:** MkDocs 2.0 drops the plugin and theme systems Material depends on.
    **Fix:** pin `mkdocs>=1.6,<2`; noted in ADR-0002.
    **Lesson:** read what your tools print, even on a green build.

!!! bug "pre-commit's `check-yaml` fails on `mkdocs.yml`: `could not determine a constructor for the tag ...python/name:...`"
    **Cause:** `!!python/name:` tells a YAML loader to import a Python function (the Mermaid formatter); the hook uses the safe loader, which refuses to.
    **Fix:** `exclude: ^mkdocs\.yml$` on that hook; the strict build validates the file.
    **Lesson:** a hook that reports "Skipped" for every file checked nothing: an earlier run with `--directory backend` silently matched no files.

!!! bug "Local preview at `http://127.0.0.1:8001/` shows nothing; the server says `Serving on http://127.0.0.1:8001/market-desk/`"
    **Cause:** `mkdocs serve` mounts the site under the path of `site_url` (`/market-desk/`, the GitHub Pages project path).
    **Fix:** open `http://127.0.0.1:8001/market-desk/`.
    **Lesson:** a feature, not a bug: local URLs match production, so path problems show up in preview.

## Check questions
??? question "Why is a broken Dockerfile caught in CI when no test touches Docker?"
    The `docker` job in `ci.yml` runs `docker build`, which executes every instruction (base image pull, `uv sync --locked`, `COPY`). Any failing step fails the job. The build itself is the check.

??? question "You edit `docs/journal/sprint-0/index.md` and save while `make docs-serve` is running. What happens in the browser?"
    MkDocs notices the change (it watches the files with `watchdog`), rebuilds the site, and the open tab refreshes by itself with the updated page.

??? question "You delete `docs/index.md`. Does `make docs-build` notice?"
    Yes, but only because of `--strict`. The explicit `nav` lists `index.md`, so MkDocs warns "a reference to 'index.md' is included in the nav… not found". Without `--strict` it still builds, and the site root is a 404. With an automatic nav there would be no warning at all, just no home page.

??? question "A PR changes only `backend/src/market_desk/api/main.py`. Which workflows run? And a PR that changes only `Makefile`?"
    Only CI for the first: `ci.yml` has no path filter, so it runs on every PR; none of Docs' paths match. For the `Makefile` PR, both: CI always runs, and `Makefile` is in Docs' path list because the `docs-build` recipe lives there. Docs watches more than `docs/`: also `mkdocs.yml`, `backend/pyproject.toml`, `backend/uv.lock` and the workflow file itself, everything that can change how the site builds.

??? question "Someone moves `pages: write` and `id-token: write` to the workflow-level `permissions:`. The site still deploys. What got worse?"
    Every job's token gets those permissions, not just deploy's. The one that matters is `build`: it runs on every PR and executes third-party code (setup-uv, MkDocs and its plugins, every package in the docs group). A compromised dependency there could mint an OIDC token or publish to Pages. Least privilege means the job that runs other people's code gets read-only, and only the small job with nothing but `deploy-pages` gets write.

## Guided exercise
**Task (type):** A: misspell an anchor in a link (`07-ci.md#guided-excercise`), predict what `make docs-serve` and `make docs-build` do and what a PR's checks would show, then fix it (break on purpose). B: write Sprint 0's "Explain it in 2 minutes" on the sprint overview, plus a self-test question.

**Outcome:** A done (2026-10-14): predictions matched the run: `docs-serve` warns and keeps serving, `docs-build` aborts with `Error 1`, and on a PR the Docs `build` job fails at the Build step. B was written by Claude on request; [the section is on the sprint overview](index.md#explain-it-in-2-minutes).

**What I got wrong:** said the failed build is what stops `deploy` on a PR; `deploy` is skipped on every PR by `if: github.ref == 'refs/heads/main'`, green build or not. `needs:` is what protects the live site on `main`: a red build there means no deploy, and the last good version stays up.

**Lesson:** a strict build is a link checker that turns a typo into a red PR; `needs:` and `if:` are two different gates (order vs condition).

## Explain it in 2 minutes
The project's learning journal is a static site built with MkDocs Material from the same Markdown files I write as I work, so there's one source of truth and the site is only a view of it. Each task has its own page: what and why, decisions with alternatives, concepts, gotchas, check questions with hidden answers for self-testing, and the guided exercise. Review pages link every concept and gotcha across sprints. The build runs in strict mode with anchor validation, so a broken link or a missing page fails the build. A separate GitHub Actions workflow builds it on PRs that touch the docs and deploys it to GitHub Pages on `main`. The deploy job is the only one with write permissions: it authenticates with a short-lived OIDC token instead of pushing generated HTML to a branch. MkDocs is pinned below 2.0 because that release drops the plugin system Material depends on.
