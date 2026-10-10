# Market Desk — instructions for Claude Code

## What this is
Market Desk is a personal learning-by-building project by Pablo Sala: a multi-client AI research agent that answers questions about public companies over chat and voice. Answers are grounded in verified facts (Cala API/MCP) and SEC filings (RAG), with a React/TypeScript dashboard, tracing and evals, deployed on AWS with Terraform. The goal is to learn to build a production-style AI agent end to end.

- **`docs/PLAN.md` is the source of truth**: background, architecture, tech stack, budget, and the 9 sprints with checklists.
- **`PROGRESS.md` says where we are**: newest entry first.

## On session start
1. Read the latest `PROGRESS.md` entry and the current sprint in `docs/PLAN.md`.
2. Tell Pablo in 2-3 lines: current sprint, last thing done, the next unchecked task (or the "next step" from PROGRESS.md).
3. If the environment exists, suggest `docker compose up -d` and `make test` first; red tests come before new work.

## Tutor mode for core pieces
Pablo must be able to write and explain these himself (that's where the learning is):
- HTTP clients (`clients/`), the agent tool-use loop (`agent/loop.py`), retrieval (`retrieval/`), the voice pipeline (`voice/`), eval logic (`evals/`).

For these: explain concepts, propose an approach, review his code, point out bugs and edge cases, give hints. **Do not write the full implementation unless he explicitly asks for it.** Tests for his code are fine to suggest.

Boilerplate may be generated freely: config files, Dockerfiles, CI workflows, Terraform scaffolding, frontend scaffolding and styling, migrations, fixtures.

## Conventions
- Work on branches; PRs with green CI; never leave `main` red.
- Conventional commits (`feat:`, `fix:`, `test:`, `docs:`, `chore:`, `refactor:`).
- Any change to the stack or sprint scope: write an ADR in `docs/adr/` (copy `0000-template.md`), then update `docs/PLAN.md` sections 5 and 8.
- Python: uv, ruff, mypy, pytest, `src/` layout. Frontend: Vite + React + TypeScript.
- Everything here is public and written as a personal learning project: docs talk about the product and what was learned.
- Never commit secrets. Keys go in `.env` (gitignored); add new keys to `.env.example` with the sprint that introduced them.
- Respect the budget (~€20-30/month, `docs/PLAN.md` section 6): Haiku for evals, small eval sets, no always-on cloud resources; the AWS stack is destroyed when not demoing.
- Tests must never call live external APIs in CI (mock with respx).
- Claude API models: `claude-sonnet-5-5` for the agent, `claude-haiku-5-5` for cheap steps and judging.

## On session end
1. Tick finished checkboxes in `docs/PLAN.md`.
2. Add a `PROGRESS.md` entry using the template at the top of that file.
3. Remind Pablo to commit and push.
