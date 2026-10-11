# ADR-0001: Containerise the API in Sprint 0

- **Date:** 2026-10-11
- **Status:** accepted
- **Sprint:** 0

## Context
Sprint 0's "Done when" says `docker compose up` gives a `/health` endpoint backed by Postgres, which only holds if the API itself runs in Compose. The plan, however, only creates the backend Dockerfile in Sprint 7 (Ship to AWS). Until then the API runs on the host with `uv run uvicorn`, so "works in a container" is untested for six sprints.

## Options considered
1. **Dockerfile + `api` Compose service in Sprint 0**: the "Done when" becomes literally true; one command starts the whole stack; container problems (paths, env vars, migrations on start) surface early while the app is tiny. Cons: ~1h more in Sprint 0; the image must be kept working as dependencies grow (CI build check helps).
2. **Keep it in Sprint 7**: Sprint 0 stays at ~4h and day-to-day dev is unchanged. Cons: "Done when" has to be reworded; first container build happens together with all the AWS work, so any problem mixes Docker and cloud issues at once.

## Decision
Option 1. Add a multi-stage uv Dockerfile for the API and an `api` service in `docker-compose.yml` in Sprint 0, right after Alembic is set up so the container can run migrations on start. Day-to-day development can still use `uv run uvicorn --reload` against the Compose database.

## Consequences
- Sprint 0 grows from ~4h to ~5h; total effort ~88h → ~89h.
- Sprint 7 reuses and hardens the existing image (ECR push, production settings) instead of creating it.
- CI should build the image so a broken Dockerfile is caught on the PR, not at deploy time.
- `docs/PLAN.md` section 8 updated (Sprint 0 task list and hours, Sprint 7 note). Section 5 unchanged: Docker is already in the stack.
