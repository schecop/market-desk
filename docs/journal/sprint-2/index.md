# Sprint 2 — Agent core

**Dates:** 2026-10-24 → · **Hours:** ~4h so far (estimate ~12h) · **Plan:** [PLAN.md, Sprint 2](../../PLAN.md#8-sprints)

## Goal (in my own words)
Build the agent itself: a tool-using loop written by hand on the Claude API, then the same flow in LangGraph to see what a framework adds and hides, and the same tools exposed over MCP. The loop is where an agent's production concerns live: step limits, tool errors, parallel calls, cost, and asking a human before anything that writes.

## Tasks
| # | Task | Page |
|---|---|---|
| 1 | `tools/`: typed tool functions (Cala facts, EDGAR filings, watchlist) | [link](01-agent-tools.md) |
| 2 | DB tables: clients, watchlists, conversations, messages, tool_calls | [link](02-agent-tables.md) |

## Sprint-level decisions
| Date | Decision | Why | Alternatives considered | ADR |
|---|---|---|---|---|
| 2026-10-24 | Cala and EDGAR split by question type: exact facts and relationships → Cala (`get_company_facts`); what a company says (risks, strategy) → filings (`search_filings`). Refined as each tool is used | Answers the open question from [Sprint 1](../sprint-1/index.md#open-questions); the tool descriptions carry this rule to the model | Expose only one source (loses verified facts or the narrative); let the model guess with no guidance in the descriptions | — |
| 2026-10-24 | The plan's "ADR-0004: hand-written loop vs LangGraph" takes the next free number when written: 0004 is the EDGAR client | Keep ADR numbers unique and in order | Renumber old ADRs (breaks links) | — |

## Open questions
- [ ] When a tool fails, who rolls back the session? `add_to_watchlist` adds the entry before calling `list_filings`; if that call fails, the entry stays pending, and a later commit would save it without its baseline. Decide in task 3 (the loop) — see [task 1, gotchas](01-agent-tools.md#gotchas).
- [ ] Alerts are still global: one event per filing whichever clients watch it. Per-client alert channels need a per-client outbox (Sprint 8). See [ADR-0007](../../adr/0007-clients-and-conversation-data-model.md#consequences).
- [ ] What shape do Cala's property `sources` really have? The fixtures only ever had `[]`; `get_company_facts` reads them tolerantly. One live call settles it.

## Retrospective (at sprint end)
