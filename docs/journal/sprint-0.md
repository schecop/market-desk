# Sprint 0 — Scaffold

**Dates:** 2026-10-10 → · **Hours:** 0h · **Plan:** [docs/PLAN.md, Sprint 0](../PLAN.md#sprint-0--scaffold-4h)

## Goal (in my own words)
A clean, professional skeleton every later sprint builds on: an installable Python package, a FastAPI service backed by Postgres in Docker, automated lint/type/test checks, and CI on every PR. Everything later depends on it.

## Decisions log
| Date | Decision | Why | Alternatives considered | ADR |
|---|---|---|---|---|
| 2026-10-10 | Standalone public repo outside OneDrive (`C:\Users\pablo\PP\market-desk`) | OneDrive syncing `.venv`, `node_modules` and Docker volumes causes slowness and file locks; GitHub is the backup | Inside an existing workspace folder; OneDrive folder | — |
| 2026-10-10 | Learning protocol in `CLAUDE.md` (explain before acting, walk through after, journal everything) | This is a learning project: understanding and a re-readable trace matter more than speed | Let Claude generate freely and review at the end | — |

## Concepts
_(fill in as you go)_

## Code map
| File | What it does | Why it exists / why this way |
|---|---|---|
| `docs/PLAN.md` | The project guide | Restart from any point without context |
| `CLAUDE.md` | Rules for Claude Code sessions | Tutor mode + learning protocol |
| `PROGRESS.md` | Session log | Where we are and the next step |
| `docs/journal/` | Learning trace per sprint | Decisions, concepts, code map, bugs, kept for later |

## Gotchas and bugs
| Symptom | Cause | Fix | Lesson |
|---|---|---|---|
| | | | |

## Commands and snippets worth keeping
```bash
```

## Open questions
- [ ] ...

## Retrospective (at sprint end)
