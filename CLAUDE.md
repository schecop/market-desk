# Market Desk — instructions for Claude Code

## What this is
Market Desk is a personal learning-by-building project by Pablo Sala: a multi-client AI research agent that answers questions about public companies over chat and voice. Answers are grounded in verified facts (Cala API/MCP) and SEC filings (RAG), with a React/TypeScript dashboard, tracing and evals, deployed on AWS with Terraform. The goal is to learn to build a production-style AI agent end to end.

- **`docs/PLAN.md` is the source of truth**: background, architecture, tech stack, budget, and the 9 sprints with checklists.
- **`PROGRESS.md` says where we are**: newest entry first.

- **`docs/journal/sprint-N.md` is the learning trace**: decisions, concepts, code map, bugs, per sprint.

## Learning protocol (applies to every action, boilerplate included)
This is a learning project first. Pablo must always know what is being done, why, and what code exists. Speed is secondary.

1. **Explain before acting.** Before writing code, running a non-trivial command or changing config, say in a few lines: what you're about to do, why, the main alternative(s) and why not, and what concept it teaches. For anything beyond a trivial edit, wait for Pablo's go-ahead.
2. **No silent changes.** After every change, list the files touched and walk through the important lines: what each part does and why it's written that way. Generated boilerplate (Docker, CI, Terraform, config, frontend scaffolding) gets explained too: generated never means unexplained.
3. **One task at a time.** Small steps Pablo can follow; don't batch unrelated changes.
4. **Check understanding on core pieces.** After a core piece works, ask Pablo one or two short questions (predict a behaviour, explain an edge case, what breaks if X changes). Keep it brief, not an exam.
5. **Record as you go**, in `docs/journal/sprint-N.md`:
   - every decision with real alternatives → Decisions log (date, decision, why, alternatives); lasting architectural ones (library, provider, data model, architecture) also get an ADR in `docs/adr/`
   - every new concept → Concepts, written so Pablo can re-read it months later
   - every new or changed file that matters → Code map (file, what it does, why it exists)
   - every bug or surprise → Gotchas (symptom, cause, fix)
6. **Explain the why in git.** Commit bodies say why, not just what. PRs use `.github/pull_request_template.md` (what, why, how, decisions, learned, verified).
7. **When a task is finished**, summarise in 3-5 lines: what was built, the key decision, the concept learned, and where it's recorded.

## On session start
1. Read the latest `PROGRESS.md` entry, the current sprint in `docs/PLAN.md`, and the current sprint journal.
2. Tell Pablo in 2-3 lines: current sprint, last thing done, the next unchecked task (or the "next step" from PROGRESS.md).
3. If the environment exists, suggest `docker compose up -d` and `make test` first; red tests come before new work.

## Tutor mode for core pieces
Pablo must be able to write and explain these himself (that's where the learning is):
- HTTP clients (`clients/`), the agent tool-use loop (`agent/loop.py`), retrieval (`retrieval/`), the voice pipeline (`voice/`), eval logic (`evals/`).

For these: explain concepts, propose an approach, review his code, point out bugs and edge cases, give hints. **Do not write the full implementation unless he explicitly asks for it.** Tests for his code are fine to suggest.

Boilerplate may be generated (config files, Dockerfiles, CI workflows, Terraform scaffolding, frontend scaffolding and styling, migrations, fixtures), always following the learning protocol above: explained before and walked through after.

## Conventions
- Work on branches; PRs with green CI; never leave `main` red.
- Conventional commits (`feat:`, `fix:`, `test:`, `docs:`, `chore:`, `refactor:`).
- Lasting architectural decisions (library, provider, data model, architecture) and any change to the stack or sprint scope: write an ADR in `docs/adr/` (copy `0000-template.md`); if the stack or scope changed, update `docs/PLAN.md` sections 5 and 8.
- Python: uv, ruff, mypy, pytest, `src/` layout. Frontend: Vite + React + TypeScript.
- Everything here is public and written as a personal learning project: docs talk about the product and what was learned.
- Never commit secrets. Keys go in `.env` (gitignored); add new keys to `.env.example` with the sprint that introduced them.
- Respect the budget (~€20-30/month, `docs/PLAN.md` section 6): Haiku for evals, small eval sets, no always-on cloud resources; the AWS stack is destroyed when not demoing.
- Tests must never call live external APIs in CI (mock with respx).
- Claude API models: `claude-sonnet-5-5` for the agent, `claude-haiku-5-5` for cheap steps and judging.

## On session end
1. Tick finished checkboxes in `docs/PLAN.md`.
2. Make sure the sprint journal is up to date (decisions, concepts, code map, gotchas from this session).
3. Add a `PROGRESS.md` entry using the template at the top of that file.
4. Remind Pablo to commit and push.
