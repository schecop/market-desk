# Gotchas

Every bug and surprise, by symptom, linking to the task page with the cause, fix and lesson. Useful when something looks familiar: search this page for the error message.

<!-- Add one line per new gotcha: [Symptom](../sprint-N/NN-page.md#gotchas) · *Task title*. -->

## Sprint 0 — Scaffold
- [`StarletteDeprecationWarning: Using httpx with starlette.testclient is deprecated`](../sprint-0/01-package-and-health.md#gotchas) · *1. Package and health endpoint*
- [`uv` / `gh`: "command not found" right after installing](../sprint-0/01-package-and-health.md#gotchas) · *1. Package and health endpoint*
- ["LF will be replaced by CRLF" warnings on `git add`](../sprint-0/01-package-and-health.md#gotchas) · *1. Package and health endpoint*
- [Health test fails with `ArgumentError: Could not parse SQLAlchemy URL`, only when run after the config test](../sprint-0/02-postgres-and-readiness.md#gotchas) · *2. Postgres and a readiness check*
- [Every `docker` command returns `500 Internal Server Error ... dockerDesktopLinuxEngine`](../sprint-0/02-postgres-and-readiness.md#gotchas) · *2. Postgres and a readiness check*
- [(2026-10-14) 3 DB tests fail with `ConnectionTimeout`; `docker compose ps` shows no containers](../sprint-0/02-postgres-and-readiness.md#gotchas) · *2. Postgres and a readiness check*
- [(avoided) `.env` at repo root ignored when running from `backend/`](../sprint-0/02-postgres-and-readiness.md#gotchas) · *2. Postgres and a readiness check*
- [`alembic current` hangs for minutes](../sprint-0/03-sqlalchemy-and-alembic.md#gotchas) · *3. SQLAlchemy sessions and Alembic*
- [`CommandError: No 'script_location' key found` in a test](../sprint-0/03-sqlalchemy-and-alembic.md#gotchas) · *3. SQLAlchemy sessions and Alembic*
- [Stairway test fails with `DuplicateTable: relation "watchlist" already exists` even after fixing `downgrade()`](../sprint-0/03-sqlalchemy-and-alembic.md#gotchas) · *3. SQLAlchemy sessions and Alembic*
- [(exercise) `migrate` exits non-zero with `Connection refused`; `api` never starts](../sprint-0/04-dockerfile.md#gotchas) · *4. Dockerfile and the containerised stack*
- [(exercise) 6 tests green, mypy `Returning Any from function declared to return "bool" [no-any-return]`](../sprint-0/05-lint-types-precommit.md#gotchas) · *5. Lint, types, test config and pre-commit*
- [(found 2026-10-14) `make help` in Git Bash: `syntax error near unexpected token '('`](../sprint-0/06-makefile.md#gotchas) · *6. Makefile*
- [CI job fails in 1s with no steps: `Unable to resolve action astral-sh/setup-uv@v10, unable to find version v10`](../sprint-0/07-ci.md#gotchas) · *7. GitHub Actions CI*
- [CI cache key ends in `no-dependency-glob`](../sprint-0/07-ci.md#gotchas) · *7. GitHub Actions CI*
- [A commit passes pre-commit while the repo has a lint error](../sprint-0/07-ci.md#gotchas) · *7. GitHub Actions CI*
- [First strict build fails: `Doc file 'PLAN.md' contains a link '../PROGRESS.md', but the target is not found`](../sprint-0/08-journal-site.md#gotchas) · *8. Journal site*
- [A broken `#anchor` link passes `--strict`](../sprint-0/08-journal-site.md#gotchas) · *8. Journal site*
- [The build prints a long warning from the Material team about MkDocs 2.0](../sprint-0/08-journal-site.md#gotchas) · *8. Journal site*
- [Local preview at `http://127.0.0.1:8001/` shows nothing; the server says `Serving on http://127.0.0.1:8001/market-desk/`](../sprint-0/08-journal-site.md#gotchas) · *8. Journal site*
- [pre-commit's `check-yaml` fails on `mkdocs.yml`: `could not determine a constructor for the tag ...python/name:...`](../sprint-0/08-journal-site.md#gotchas) · *8. Journal site*
- [The rule I asked for doesn't match what the API returns](../sprint-0/09-branch-protection.md#gotchas) · *9. Branch protection*
- [I said the badge would show any branch's latest run without `?branch=main`](../sprint-0/10-readme.md#gotchas) · *10. README*
- [Cleaning up the fresh clone removed `market-desk-api:latest`, the image the real repo uses](../sprint-0/10-readme.md#gotchas) · *10. README*
- [`make help | head -3` ends with `make: *** [Makefile:14: help] Error 3328`](../sprint-0/10-readme.md#gotchas) · *10. README*

## Sprint 1 — Integrations layer
- [The key loaded but had length 0](../sprint-1/01-cala-signup.md#gotchas) · *1. Cala sign-up and API key*
- [Two error shapes in one API](../sprint-1/01-cala-signup.md#gotchas) · *1. Cala sign-up and API key*
- [The `transport` parameter was accepted but never used](../sprint-1/02-cala-client.md#gotchas) · *2. Cala client*
- [Tests changed to match the code instead of the requirement](../sprint-1/02-cala-client.md#gotchas) · *2. Cala client*
- [My own skeleton test contradicted the rule](../sprint-1/02-cala-client.md#gotchas) · *2. Cala client*
- [`staticmethod` used with a non-method, and the client lost two methods](../sprint-1/02-cala-client.md#gotchas) · *2. Cala client*
- [`object list can't be used in 'await' expression`, deep inside httpx2](../sprint-1/02-cala-client.md#gotchas) · *2. Cala client*
- [Only two relationship types worked](../sprint-1/02-cala-client.md#gotchas) · *2. Cala client*
- [`'FieldInfo' object has no attribute 'items'`](../sprint-1/03-edgar-client.md#gotchas) · *3. EDGAR client*
- [Retrying forever: tenacity's default is `stop_never`](../sprint-1/03-edgar-client.md#gotchas) · *3. EDGAR client*
- [The cache stored errors](../sprint-1/03-edgar-client.md#gotchas) · *3. EDGAR client*
- [`UnicodeEncodeError: 'charmap' codec can't encode character '\u2192'`](../sprint-1/03-edgar-client.md#gotchas) · *3. EDGAR client*
- [I found `edgartools` only after building the client](../sprint-1/03-edgar-client.md#gotchas) · *3. EDGAR client*
- [The library raises `ValueError` for a malformed signature header](../sprint-1/05-webhooks.md#gotchas) · *5. Webhooks*
- [Every valid event came back 422](../sprint-1/05-webhooks.md#gotchas) · *5. Webhooks*
- [The dispatcher reported every successful delivery as a failure](../sprint-1/05-webhooks.md#gotchas) · *5. Webhooks*
- [A hand-computed signature didn't match the library's](../sprint-1/05-webhooks.md#gotchas) · *5. Webhooks*
