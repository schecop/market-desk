# Sprint 1 — Integrations layer

**Dates:** 2026-10-16 → · **Hours:** in progress · **Plan:** [PLAN.md, Sprint 1](../../PLAN.md#8-sprints)

## Goal (in my own words)
Typed, production-grade clients for the two data sources (Cala and SEC EDGAR), plus inbound and outbound webhooks. Integrations are where real systems break: auth, retries, rate limits, pagination and signatures.

## Tasks
| # | Task | Page |
|---|---|---|
| 1 | Cala sign-up, API docs, key in `.env` | [link](01-cala-signup.md) |

## Sprint-level decisions
| Date | Decision | Why | Alternatives considered | ADR |
|---|---|---|---|---|
| 2026-10-16 | Treat Cala's free tier (100 calls in total) as a hard budget: tests always mock it (respx), development uses a local response cache, live calls only on purpose | 100 calls run out in one careless afternoon of debugging; once spent, the integration can't be checked | Call the live API while developing (burns the quota); a paid tier (outside the budget) | ADR-0003 (client design), pending |

## Open questions
- [ ] Stairway test runs `downgrade base` on the **dev** DB (carried over from [Sprint 0](../sprint-0/index.md#open-questions)). Decide before the first model (watchlist).
- [x] Cala pagination: no cursor anywhere. `GET /v1/entities` has only `limit` (max 100); relationships on `POST /v1/entities/{id}` use `limit`/`offset`. See [task 1](01-cala-signup.md#what-the-cala-api-looks-like).
- [ ] Is a `429` from Cala "too fast" or "quota spent"? The spec doesn't say. Find out (cheaply) in task 2.

## Retrospective (at sprint end)
