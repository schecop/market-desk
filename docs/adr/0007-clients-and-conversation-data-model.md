# ADR-0007: Clients and the conversation data model

- **Date:** 2026-10-24
- **Status:** accepted
- **Sprint:** 2

## Context
Market Desk is multi-client: each client has its own watchlist and, from Sprint 4, its own prompt, tone and voice. The agent arrives in this sprint, and the Claude API is stateless: every call carries the whole conversation, so the history has to be stored. Task 4 also needs somewhere to park a write tool waiting for a human's approval. The existing `watchlist` table (Sprint 1) already holds real rows with no client.

## Options considered
**Tenancy**
1. **A `client_id` column on every client-owned table, filtered in every query**: one database and one schema; the risk is a query that forgets the filter.
2. Schema or database per client: strong isolation, but migrations per client and far more moving parts than a learning project with two clients needs.

**Watchlist shape**
1. **`client_id` on the existing table**, unique per `(client_id, ticker)`, renamed to `watchlists`.
2. A `watchlists` table plus `watchlist_entries`, so a client can have several named lists: nothing in the product needs it.

**Message content**
1. **JSONB with the API's content blocks** (text, tool_use, tool_result) as they were sent and received: the conversation can be replayed to the model unchanged, and `tool_result` blocks keep pointing at their `tool_use_id`.
2. Plain text: loses the tool blocks, so a conversation with tool calls can't be resumed.
3. One table per block type: many joins for something always read whole.

**Tool calls**
1. **A `tool_calls` table that duplicates the tool_use block on purpose**: the message is what the model saw, the row is what we ran (input, output, error, duration, approval status), queryable without digging through JSON.
2. Only the blocks inside `messages`: no duplication, but "which tools fail?" or "what is pending approval?" become JSON queries, and there's nowhere natural for approval state.

**Ids**
1. **UUID for conversations, integers elsewhere**: the conversation id appears in our API and URLs, so it shouldn't be guessable; messages and tool calls are only reached through their conversation, and integers are smaller and give message order for free.
2. Integers everywhere: simpler, but `/conversations/42` invites guessing.
3. UUIDs everywhere: no benefit for rows never addressed from outside.

## Decision
Tenancy option 1 with watchlist option 1, JSONB content blocks, a separate `tool_calls` table, and UUID conversation ids. `clients` (slug, name) → `watchlists`, `conversations` → `messages` → `tool_calls`. Deleting a conversation cascades to its messages and tool calls; a client with data can't be deleted (`RESTRICT`). `role` and `status` are strings guarded by CHECK constraints, not Postgres enums, so adding a value is a one-line migration. Existing watchlist rows moved to a `default` client through an expand → backfill → contract migration.

## Consequences
- Every query on client-owned data must filter by `client_id`, and the client always comes from the request (the API key, task 5), never from the model's tool arguments. `ToolContext.client_id` carries it to the tools.
- A UUID makes ids hard to guess but isn't access control: the `client_id` filter is.
- Alerts stay global: one event per filing, whichever clients watch it. Per-client alert channels (Sprint 8) need a per-client outbox.
- The migration's downgrade keeps only the default client's watchlist rows (one table can't hold two clients' copies of a ticker under a unique ticker).
- Storing raw content blocks ties the schema to the Claude API's message format; LangGraph (task 7) or another provider would need a translation layer.
