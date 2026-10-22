# Market Desk — Project Guide

> The single source of truth for this project. If you are starting fresh (new day, new machine, new Claude Code session, after weeks away), start at **Section 1**.

**Status lives in [`PROGRESS.md`](https://github.com/schecop/market-desk/blob/main/PROGRESS.md).** This file holds the plan; tick its checkboxes as you go.

| | |
|---|---|
| Owner | Pablo Sala |
| Started | 2026-10-10 |
| Total effort | ~90.5h over 9 sprints (Sprint 0-8), about 9 weeks at ~10h/week |
| Budget | up to ~€20-30/month for paid services |
| Checkpoint | after Sprint 3 (~40.5h): first usable version |

---

## Contents
1. [How to use this guide](#1-how-to-use-this-guide)
2. [Why this project exists](#2-why-this-project-exists)
3. [Product overview](#3-product-overview)
4. [Architecture](#4-architecture)
5. [Tech stack](#5-tech-stack)
6. [Budget and guardrails](#6-budget-and-guardrails)
7. [Repo layout](#7-repo-layout)
8. [Sprints](#8-sprints)
9. [Out of scope](#9-out-of-scope)
10. [After the project](#10-after-the-project)

---

## 1. How to use this guide

### Start of every session (5 minutes)
1. Read the **latest entry in `PROGRESS.md`**: what was done, the next step, blockers.
2. Open the **current sprint** in Section 8 and find the first unchecked box.
3. Bring the environment up (once Sprint 0 exists): `docker compose up -d` then `make test`. If tests are red, fixing them is the first task.
4. Work on **one checkbox at a time**, on a branch, ending in a PR. Each checkbox follows the task lifecycle in `CLAUDE.md`: explain → build → walk-through → check questions → **guided exercise you do yourself** → verify → journal → commit (only when you say so).

### End of every session (5-10 minutes)
1. Tick the boxes you finished in this file.
2. Update the journal (`docs/journal/sprint-N/`, one page per task): decisions, concepts, code map, gotchas, check questions from this session.
3. Add a `PROGRESS.md` entry: date, what you did, what you learned, **the exact next step**, blockers, hours spent.
4. Commit any finished task that is still uncommitted (only once its guided exercise is done), then push. **Never leave `main` with red CI.**

### Learning first: the trace you keep
This is a hands-on learning project, so understanding matters more than speed. For every action you should know **what** is being done, **why**, and **which code** results, and be able to look it up later:

| Record | Where |
|---|---|
| Where we are, next step, what I learned this session | `PROGRESS.md` |
| Decisions (with alternatives), concepts, code map, bugs, check questions | `docs/journal/sprint-N/`, one page per task (published as the journal site) |
| Lasting architectural decisions | `docs/adr/` |
| Why each change was made | commit bodies and PR descriptions (`.github/pull_request_template.md`) |

`CLAUDE.md` enforces this for Claude Code sessions: explain before acting, walk through every change afterwards (boilerplate included), one task at a time, short understanding checks, a **guided exercise after every task** (complete code, build or extend a feature, fix a bug, write a test), journal entries as you go, and **no commit until the exercise is done and you say so**.

### Restarting after a long break
Re-read Sections 2-4 (why, what, how it fits together), then follow "Start of every session". The "Background" block in each sprint explains its concepts from scratch.

### Working with Claude Code
`CLAUDE.md` at the repo root tells any Claude Code session how to behave here. In short: Claude may generate boilerplate, config and scaffolding (always explained before and after), but for the **core pieces** (API clients, the agent loop, retrieval, voice pipeline, eval logic) it acts as a **tutor and reviewer**. You write them, and you must be able to explain every line.

### Changing the plan
Plans change. When you change a technology or a sprint (or make any lasting architectural decision), write a short ADR in `docs/adr/` (copy `0000-template.md`), then update Sections 5 and 8 here. The plan should always describe reality.

---

## 2. Why this project exists

### The goal
Learn to build a production-style AI agent end to end, by hand: backend services and integrations, a tool-using agent outside any framework, retrieval with real evaluation, a web UI, a voice channel, observability and a cloud deployment. Pablo's background is data engineering and technical leadership, with Claude Code agents and MCP in production; this project fills in the parts of the stack he hasn't built himself yet.

### What it covers
| Area | What gets built |
|---|---|
| Backend services & integrations | FastAPI, Postgres, typed REST clients, auth, webhooks |
| Tool-using agents | Own tool-use loop on the Claude API, compared with LangGraph; an MCP server |
| Full-stack web | React + TypeScript dashboard |
| Software engineering practices | Tests, CI/CD, containers, deployment, IaC |
| LLM observability and evals | Tracing, eval sets, evals as a CI gate, debugging live agents |
| Voice agents | Streaming STT/TTS, latency budget, transcription tuning |
| RAG / retrieval | Hybrid search and reranking, measured with evals |
| Product and docs | Multi-client onboarding through config, developer docs, n8n automation, financial data |

### Why one project, and why this one
One product touches all of this in a realistic way: an agent that real users talk to (chat and voice), built on third-party APIs, grounded in retrieval, with a web UI, per-client config, tracing, evals and a cloud deployment. Building it for several "clients" makes the integration work concrete: **you are your own first customer.** Finance is a domain Pablo already cares about, which keeps motivation up.

### Ground rules
1. **Public from day 1.** Built in the open, with steady small commits.
2. **PRs with green CI**, even working alone.
3. **Demoable at the end of every sprint.** There is always something that works end to end.
4. **Write the core yourself** (API clients, agent loop, retrieval, evals). That's where the learning is.
5. **Measure things.** Retrieval hit-rate, latency, cost, transcription error rate. Numbers show whether a change really helped.

---

## 3. Product overview

**Market Desk** is a multi-client AI research agent that answers questions about public companies, over **chat and voice**. Every answer is grounded in **verified structured facts** (Cala's knowledge graph, via API and MCP) and **SEC filings** (via retrieval), with citations.

### User stories
1. **Analyst, chat:** "Compare the main risk factors of the companies on my watchlist." The agent plans, calls tools (Cala facts, filing search, watchlist), and returns a cited answer in the dashboard.
2. **Analyst, voice:** asks out loud "What was ASML's revenue last year and what are its biggest risks?" and gets a spoken, sourced answer within a few seconds.
3. **Integration engineer:** onboards a new client (its own watchlist, system prompt, tone, voice and enabled tools) **through configuration only**, in under 30 minutes, and sets up an alert when a watched company files a new 10-K.

### Non-goals
- No investment or trading advice, no real-time prices.
- No full user auth: a simple per-client API key is enough.
- No mobile app, no multi-region, no production SLA.

---

## 4. Architecture

```
                 ┌──────────────────────────────┐
  Browser ─────► │  React + TypeScript dashboard│  chat · voice · watchlist · client settings · traces
                 └──────────────┬───────────────┘
                     REST + WebSocket (voice)
                 ┌──────────────▼───────────────┐
                 │            FastAPI           │  per-client API key · webhooks in/out
                 └───┬──────────────┬───────────┘
                     │              │ voice: STT (Deepgram) → agent → TTS
                 ┌───▼──────────────▼───────────┐
                 │            Agent             │  own tool-use loop on the Claude API
                 │   (LangGraph variant, S2)    │  step limits · tool errors · human confirm on writes
                 └───┬───────┬────────┬────────┬┘
        ┌────────────▼┐ ┌────▼─────┐ ┌▼────────┐ ┌▼──────────┐
        │ Cala client │ │  EDGAR   │ │Retrieval│ │ Watchlist │
        │ (facts)     │ │  client  │ │ hybrid +│ │ & client  │
        └─────────────┘ └──────────┘ │ rerank  │ │ config    │
                                     └────┬────┘ └─────┬─────┘
                                 ┌────────▼────────────▼──────┐
                                 │  Postgres 16 + pgvector    │  app data · vectors · full-text
                                 └────────────────────────────┘
  Side paths:  outbound webhooks → n8n / Slack     tracing → Langfuse
               MCP server exposing the same tools (usable from Claude Desktop / Claude Code)
  Deployed:    ECS Fargate + RDS + S3/CloudFront, built with Terraform, deployed by GitHub Actions (OIDC)
```

**Key idea:** the tools (Cala lookup, filing search, watchlist) are plain Python functions with typed inputs and outputs. The agent loop, the LangGraph variant and the MCP server are three different ways of exposing **the same tools**.

---

## 5. Tech stack

| Layer | Choice | Why |
|---|---|---|
| Python env | Python 3.12, `uv` | Fast, modern dependency and venv management; one lockfile |
| API | FastAPI, Pydantic v2 | Typed request/response models give OpenAPI docs for free |
| DB access | SQLAlchemy 2 + Alembic | Industry standard ORM and migrations |
| Database | Postgres 16 + pgvector | One database for app data, embeddings and full-text (BM25-style) search |
| HTTP | httpx2 (async), tenacity | Maintained successor of httpx; declarative retries with backoff (ADR-0003) |
| Test mocks | `httpx2.MockTransport` | Injected fake transport so CI never hits live APIs; respx only patches `httpx` (ADR-0003) |
| Quality | pytest, ruff, mypy, pre-commit | Tests, lint/format, types, enforced before commit |
| CI/CD | GitHub Actions | Free for public repos; OIDC to AWS in Sprint 7 |
| Journal site | MkDocs Material on GitHub Pages | Searchable learning journal built from the Markdown in `docs/journal/`; free hosting, deployed by GitHub Actions ([ADR-0002](adr/0002-journal-site-mkdocs-github-pages.md)) |
| LLM | Claude API (`anthropic` SDK): `claude-sonnet-5-5` for the agent, `claude-haiku-5-5` for cheap steps and evals | Strong tool use; Haiku and prompt caching keep cost down |
| Agent framework | LangGraph (comparison only) | Widely used agent framework; contrast with the hand-written loop |
| MCP | Official MCP Python SDK | Same tools exposed as an MCP server, like Cala's own |
| Embeddings / rerank | Local sentence-transformers model + local cross-encoder | Zero cost, offline, good enough for 10-20 companies |
| Data | Cala API (free Starter tier); SEC EDGAR APIs (free) | Verified facts + unstructured filings. EDGAR requires a User-Agent with contact email and has rate limits |
| Automation | n8n (self-hosted in Docker), Slack incoming webhook | A common way to wire agents into business workflows; Cala integrates with n8n |
| Frontend | Vite + React + TypeScript, TanStack Query, Tailwind, Vitest | Mainstream frontend stack: fast dev server, typed components, cached data fetching |
| API types | openapi-typescript (generated from FastAPI's schema) | Backend and frontend stay in sync |
| Voice | Browser mic over WebSocket; STT: Deepgram; TTS: Deepgram or ElevenLabs; optional phone number via Twilio | Free starting credits (check at the time); phone line only if budget allows |
| Observability | Langfuse (free hobby cloud tier or self-hosted) | Traces, cost and latency per LLM/tool call |
| Cloud | AWS: ECR, ECS Fargate, RDS Postgres, S3 + CloudFront, Secrets Manager | Managed building blocks; hands-on practice for AWS SAA-C03 |
| IaC | Terraform | Infrastructure as reviewable code; `apply` for demos, `destroy` after |

Any change here needs an ADR in `docs/adr/`.

---

## 6. Budget and guardrails

Target: **≤ €20-30/month.** Daily development runs locally in Docker at zero cost.

| Service | Expected cost | Guardrail |
|---|---|---|
| Claude API | ~€5-15/month | Monthly spend limit in the Anthropic console; Haiku for evals; prompt caching; small eval sets |
| Embeddings / rerank | €0 | Local models |
| Cala, EDGAR | €0 | Free tiers; cache responses locally during development |
| Deepgram / ElevenLabs | €0 at first | Free credits first; short test clips |
| Twilio phone number | ~€1-2/month + per-minute | Optional stretch in Sprint 5 only |
| Langfuse | €0 | Hobby tier or self-hosted |
| AWS | a few € per day while up | **AWS Budgets alert at €20.** Stack is up for demos only, otherwise `terraform destroy` |

**Never commit secrets.** Keys live in `.env` (gitignored) locally and in AWS Secrets Manager in the cloud. `.env.example` lists every key with the sprint that introduces it.

---

## 7. Repo layout

Target structure (built up sprint by sprint, not created up front):

```
market-desk/
├── CLAUDE.md                instructions for Claude Code sessions
├── README.md                public face; becomes an integration guide in Sprint 8
├── PROGRESS.md              session log, newest first
├── Makefile                 make up / test / lint / eval / fmt
├── docker-compose.yml       postgres+pgvector, api, (n8n), (langfuse)
├── .env.example
├── mkdocs.yml               journal site config (MkDocs Material → GitHub Pages)
├── backend/
│   ├── pyproject.toml
│   ├── src/market_desk/
│   │   ├── api/             FastAPI routers, schemas, dependencies
│   │   ├── clients/         cala.py, edgar.py (typed HTTP clients)
│   │   ├── tools/           tool functions shared by agent, LangGraph and MCP
│   │   ├── agent/           loop.py (hand-written), graph.py (LangGraph)
│   │   ├── retrieval/       ingest, chunking, embeddings, hybrid search, rerank
│   │   ├── voice/           STT/TTS adapters, WebSocket handler
│   │   ├── mcp_server/      MCP server exposing tools/
│   │   ├── webhooks/        inbound verification, outbound dispatch
│   │   └── db/              models, session, alembic migrations
│   └── tests/
├── frontend/                Vite + React + TS app
├── evals/                   question sets, runners, results
├── infra/terraform/         AWS stack
├── .github/
│   ├── workflows/           CI/CD
│   └── pull_request_template.md   what / why / how / decisions / learned / verified
└── docs/
    ├── PLAN.md              this file
    ├── journal/             learning trace, one page per task (published as the journal site)
    └── adr/                 architecture decision records
```

---

## 8. Sprints

Each sprint uses the same template: **Objective · Why it's interesting · Background · Tech · Tasks · Done when · Explain it in 2 minutes · Docs if stuck.**

| # | Sprint | Hours | Main skills |
|---|---|---|---|
| 0 | Scaffold | ~6.5h | SWE practices, containers, docs site |
| 1 | Integrations layer | ~10h | Backend & integrations, n8n |
| 2 | Agent core | ~12h | Agents outside Claude Code |
| 3 | RAG with evaluation | ~12h | RAG, financial data |
| — | **Checkpoint: first usable version** | ~40.5h total | |
| 4 | React + TypeScript dashboard | ~12h | Full-stack web |
| 5 | Voice channel | ~12h | Voice agents |
| 6 | Observability and evals in CI | ~10h | Observability, debugging live agents |
| 7 | Ship to AWS | ~10h | Containers, deployment, IaC |
| 8 | Second client, docs and demo | ~6h | Multi-client, docs, communication |
| | **Total** | **~90.5h** | |

---

### Sprint 0 — Scaffold (~6.5h)

**Objective:** a clean, professional skeleton that every later sprint builds on.

**Why it's interesting:** everything later stands on this. Packaging, tests and CI decide whether the next 80 hours are pleasant or painful, and how a repo is set up says a lot about how it will be maintained.

**Background:** a modern Python service has a `pyproject.toml` (dependencies and tool config in one file), a `src/` layout (so tests import the installed package, not loose files), automated lint/format/type checks, and CI that runs them on every PR. Docker Compose runs the database locally exactly as it will run elsewhere.

**Tech:** uv, FastAPI, Postgres 16 + pgvector image, Docker (multi-stage build), Docker Compose, ruff, mypy, pytest, pre-commit, GitHub Actions, MkDocs Material.

**Tasks:**
- [x] `backend/pyproject.toml` with uv; `src/market_desk/` package; FastAPI app with `/health`
- [x] `docker-compose.yml` with `pgvector/pgvector` Postgres; `/health` checks the DB connection
- [x] SQLAlchemy session + Alembic initialised (first empty migration)
- [x] Multi-stage `Dockerfile` (uv) for the API + `api` service in `docker-compose.yml`; runs migrations on start ([ADR-0001](adr/0001-containerise-api-in-sprint-0.md))
- [x] ruff + mypy + pytest configured in `pyproject.toml`; pre-commit hooks
- [x] `Makefile`: `up`, `down`, `test`, `lint`, `fmt`
- [x] GitHub Actions: lint + type check + tests on PRs and on `main` (Postgres as a service container)
- [x] Journal site: MkDocs Material on GitHub Pages, one page per task, deployed by a GitHub Actions workflow on push to `main` ([ADR-0002](adr/0002-journal-site-mkdocs-github-pages.md))
- [x] Branch protection on `main`: PR + green CI required
- [x] README: one-paragraph pitch + "Status: Sprint 0"

**Done when:** `docker compose up` gives a `/health` endpoint backed by Postgres, and CI is green on a PR.

**Explain it in 2 minutes:** why `src/` layout; what runs in CI and why; how you keep a solo repo disciplined (PRs, branch protection).

**Docs if stuck:** [uv](https://docs.astral.sh/uv/) · [FastAPI](https://fastapi.tiangolo.com/) · [SQLAlchemy](https://docs.sqlalchemy.org/) · [Alembic](https://alembic.sqlalchemy.org/) · [pgvector](https://github.com/pgvector/pgvector) · [ruff](https://docs.astral.sh/ruff/) · [mypy](https://mypy.readthedocs.io/) · [pytest](https://docs.pytest.org/) · [GitHub Actions](https://docs.github.com/actions)

---

### Sprint 1 — Integrations layer (~10h)

**Objective:** typed, production-grade clients for the two data sources, plus inbound and outbound webhooks.

**Why it's interesting:** almost every useful agent sits on top of someone else's API. Auth, retries, rate limits, pagination and webhooks are where integrations break in practice, and where debugging skills matter most.

**Background:**
- **Auth styles:** API keys (header), OAuth2 (client credentials / authorization code, access + refresh tokens), signed webhooks (HMAC over the payload with a shared secret).
- **Production behaviour:** timeouts on every call; retry only what is safe (429, 5xx, network errors) with exponential backoff and jitter, honouring `Retry-After`; pagination (cursor vs offset); idempotency.
- **An "SDK"** is a thin, typed client: request building, auth, retries and error mapping in one place, returning Pydantic models instead of raw JSON.
- **Webhooks:** inbound means you verify the signature and respond fast (queue the work); outbound means you sign your payload and retry on failure.

**Tech:** httpx2, tenacity, Pydantic v2, `MockTransport`, n8n (Docker), Slack incoming webhook.

**Tasks:**
- [x] Sign up for Cala's free tier; read its API docs; store the key in `.env`
- [x] `clients/cala.py`: typed client (auth header, timeouts, retries with backoff on 429/5xx, `Retry-After`, pagination, custom exceptions); **write it yourself**
- [x] `clients/edgar.py`: company lookup (ticker → CIK), filings list, filing document fetch; required User-Agent; client-side rate limiting; local response cache for development
- [x] Unit tests with `MockTransport`: success, pagination, 429 then success, 500 exhausting retries, timeout, malformed JSON
- [x] `webhooks/`: inbound endpoint verifying an HMAC signature; outbound dispatcher with signing and retries
- [ ] n8n in Docker Compose; a flow that receives "new 10-K filed for a watchlist company" and posts to Slack
- [ ] A scheduled check (simple background task) that detects new filings for watchlist companies and fires the outbound webhook
- [x] ADR-0003: client design (sync vs async, retry policy)

**Done when:** a forced 429 is retried and logged instead of crashing, and an n8n flow receives a "new 10-K" event and posts it to Slack.

**Explain it in 2 minutes:** which errors you retry and which you don't, and why; how you'd debug a customer's failing integration (logs, request IDs, reproducing with a mock); webhook security.

**Docs if stuck:** [HTTPX2](https://github.com/pydantic/httpx2) · [Tenacity](https://tenacity.readthedocs.io/) · [Mock transports](https://www.python-httpx.org/advanced/transports/#mock-transports) · [Pydantic](https://docs.pydantic.dev/) · [SEC EDGAR APIs](https://www.sec.gov/search-filings/edgar-application-programming-interfaces) · Cala API docs (from cala.ai) · [n8n](https://docs.n8n.io/) · [Slack incoming webhooks](https://api.slack.com/messaging/webhooks)

---

### Sprint 2 — Agent core (~12h)

**Objective:** a multi-step, tool-using agent you wrote yourself on the Claude API, the same agent in LangGraph, and the tools exposed as an MCP server.

**Why it's interesting:** using agents like Claude Code shows what a good agent feels like from the outside; this is about building the loop itself: tool calls, errors, limits, state. Then the same flow in a framework, to see what it adds and what it hides.

**Background:**
- **Tool use / function calling:** you send tool definitions (name, description, JSON schema); the model replies with `tool_use` blocks; you execute them and send back `tool_result` blocks; repeat until the model answers. That loop **is** the agent.
- **Production concerns:** max steps, timeouts, tool errors returned to the model (not raised), parallel tool calls, conversation state, cost per run, and **human confirmation before write actions**.
- **Frameworks** (LangGraph) model the same loop as a graph of nodes and edges with state, checkpoints and interrupts. Useful for complex flows; extra abstraction for simple ones.
- **MCP** standardises how tools are offered to any client (Claude Desktop, Claude Code, others). Cala ships an MCP server; you'll build your own next to it.

**Tech:** `anthropic` SDK (`claude-sonnet-5-5`), LangGraph, MCP Python SDK, Postgres (watchlist and conversations tables).

**Tasks:**
- [ ] `tools/`: typed tool functions: `get_company_facts` (Cala), `search_filings` (EDGAR for now; retrieval in S3), `list_watchlist`, `add_to_watchlist`, `remove_from_watchlist`
- [ ] DB tables: clients, watchlists, conversations, messages, tool_calls
- [ ] `agent/loop.py`: hand-written tool-use loop with step limit, error handling, parallel tool calls, token/cost accounting; **write it yourself**
- [ ] Human confirmation for write tools (the agent proposes, the API waits for approval)
- [ ] `POST /chat` endpoint (streaming response) using the loop
- [ ] Tests: fake LLM responses to test the loop deterministically (tool call → result → answer; tool error; step limit hit)
- [ ] `agent/graph.py`: the same flow in LangGraph, including an interrupt for confirmation
- [ ] ADR-0004: hand-written loop vs LangGraph, trade-offs and which one the API uses
- [ ] `mcp_server/`: expose `tools/` over MCP; connect it in Claude Desktop or Claude Code next to Cala's MCP server

**Done when:** "Compare the main risks of the companies on my watchlist" runs multi-step with cited tool calls in both implementations, and the MCP server works from a Claude client.

**Explain it in 2 minutes:** walk through the loop on a whiteboard; how you stop runaway agents; when you'd pick a framework and when not; MCP vs plain function calling.

**Docs if stuck:** [Claude API docs: tool use](https://docs.anthropic.com/) · [LangGraph](https://langchain-ai.github.io/langgraph/) · [Model Context Protocol](https://modelcontextprotocol.io/)

---

### Sprint 3 — RAG with evaluation (~12h)

**Objective:** retrieval over SEC filings that measurably improves through three versions, combined with Cala facts in cited answers.

**Why it's interesting:** retrieval quality is easy to claim and hard to prove. Building three versions and measuring each one turns RAG from guesswork into an experiment, which is where a data background pays off.

**Background:**
- **Pipeline:** load → clean → chunk (size, overlap, respect section boundaries) → embed → store → retrieve top-k → (rerank) → generate with citations.
- **Hybrid search:** dense embeddings capture meaning; keyword/BM25-style search catches exact terms like tickers, product names and numbers. Combine them (e.g. reciprocal rank fusion).
- **Reranking:** a cross-encoder rescores the top ~50 candidates jointly with the query; slower but more precise.
- **Evaluation:** retrieval metrics (hit-rate@k, MRR) need a labelled set of questions → expected source chunks; answer quality is checked against expected facts (by hand or with an LLM judge on Haiku).
- **Structured + unstructured:** Cala gives verified facts (who, what, numbers, relationships); filings give context (why, risks). Good answers cite both.

**Tech:** pgvector, Postgres full-text search (`tsvector`), sentence-transformers (embedding model + cross-encoder), `claude-haiku-5-5` for judging.

**Tasks:**
- [ ] Pick 10-20 companies (mix of US large caps and foreign filers with 10-K/20-F)
- [ ] `retrieval/ingest.py`: fetch 10-K risk-factor sections via the EDGAR client; clean; chunk with section metadata
- [ ] Embed chunks locally; store in pgvector with metadata (company, filing, section, date)
- [ ] V1 naive: dense top-k; **write retrieval yourself**
- [ ] V2 hybrid: add Postgres full-text search + rank fusion
- [ ] V3 rerank: local cross-encoder over the top candidates
- [ ] `evals/retrieval.jsonl`: ~30 hand-written questions with expected chunks/facts
- [ ] `make eval`: hit-rate@5, MRR, answer correctness per version; results saved to `evals/results/`
- [ ] Switch the `search_filings` tool to retrieval; answers cite Cala facts and filing passages
- [ ] README table: V1 vs V2 vs V3 with numbers

**Done when:** the README shows a table comparing naive, hybrid and reranked retrieval, with numbers, and the agent's answers carry citations to both sources.

**Explain it in 2 minutes:** why hybrid beat (or didn't beat) dense on tickers and numbers; how you built the eval set; chunking decisions; cost/latency of reranking.

**Docs if stuck:** [pgvector](https://github.com/pgvector/pgvector) · [PostgreSQL full-text search](https://www.postgresql.org/docs/current/textsearch.html) · [Sentence Transformers](https://github.com/UKPLab/sentence-transformers)

> ### ✅ Checkpoint: first usable version (~40.5h)
> Integrations, a hand-written agent, MCP, and measured RAG on real financial data: the core of the product works end to end. Make sure the README explains it in 30 seconds and take a short break before the next half.

---

### Sprint 4 — React + TypeScript dashboard (~12h)

**Objective:** a web app where a non-technical user can chat with the agent, manage a watchlist and configure a client.

**Why it's interesting:** an agent nobody can use without a terminal isn't a product. Typed React + TypeScript, generated API types and a streaming UI close the loop from backend to user.

**Background:**
- **React:** components, props, state, effects; data fetching and caching with TanStack Query instead of hand-rolled `useEffect` calls.
- **TypeScript:** static types for the frontend; generating them from FastAPI's OpenAPI schema means a backend change that breaks the frontend fails at compile time.
- **Streaming:** the chat streams tokens (Server-Sent Events or fetch streaming) so answers appear progressively.
- **Per-client config:** the same app behaves differently per client (prompt, tone, tools, voice). One codebase, many clients: the differences live in configuration, not code.

**Tech:** Vite, React, TypeScript, TanStack Query, Tailwind, openapi-typescript, Vitest.

**Tasks:**
- [ ] Scaffold `frontend/` with Vite (React + TS); Tailwind; lint and type check in CI
- [ ] Generate API types from `/openapi.json`; a `make types` target
- [ ] Chat page: streaming answers, tool calls shown as collapsible steps, citations as links
- [ ] Approval UI for write actions proposed by the agent
- [ ] Conversation history page
- [ ] Watchlist page (add/remove companies)
- [ ] Client settings page: system prompt, tone, enabled tools, voice; backend endpoints + DB for client config
- [ ] Vitest tests for key components; frontend build in CI
- [ ] Add the frontend to Docker Compose (or a `make dev` target)

**Done when:** a non-technical user can create a watchlist and chat with the agent, with streaming answers and citations, without touching the terminal.

**Explain it in 2 minutes:** how backend and frontend stay in sync (generated types); how streaming works end to end; how per-client config flows from the UI into the agent.

**Docs if stuck:** [React](https://react.dev/) · [Vite](https://vite.dev/) · [TypeScript](https://www.typescriptlang.org/docs/) · [TanStack Query](https://tanstack.com/query/latest) · [openapi-typescript](https://github.com/openapi-ts/openapi-typescript) · [Tailwind CSS](https://tailwindcss.com/docs) · [Vitest](https://vitest.dev/)

---

### Sprint 5 — Voice channel (~12h)

**Objective:** ask questions out loud and get spoken, sourced answers, with measured latency and transcription accuracy.

**Why it's interesting:** voice is the hardest channel: every stage adds latency, and generic speech-to-text mangles tickers and company names. Making it feel natural is measurable engineering, not magic.

**Background:**
- **Voice pipeline:** audio capture → streaming speech-to-text (STT) → agent → text-to-speech (TTS) → playback. Each stage adds latency; users notice anything above ~1-2 s before the first audio.
- **Latency budget:** measure each stage per turn (STT final, LLM first token, tool calls, TTS first byte) and attack the biggest one: streaming everywhere, shorter prompts, faster models for simple turns.
- **Transcription tuning:** generic STT gets proper nouns wrong ("ASML", "BBVA", "Nvidia"). Fixes: keyword boosting / custom vocabulary where the provider supports it, plus a post-correction step that maps near-misses to your watchlist entities. Measure word error rate (WER) on entities before and after.
- **Turn-taking:** endpointing (when the user stopped talking) and barge-in (user interrupts) make voice feel natural.

**Tech:** browser MediaRecorder/Web Audio + WebSocket to FastAPI; Deepgram STT; Deepgram or ElevenLabs TTS; optional Twilio number.

**Tasks:**
- [ ] Sign up for the STT/TTS providers' free credits; keys in `.env`
- [ ] `voice/` adapters behind an interface (so providers can be swapped); **write the pipeline yourself**
- [ ] WebSocket endpoint: stream audio in, transcripts and audio out
- [ ] Mic button in the dashboard; live transcript; audio playback
- [ ] Per-turn latency breakdown logged and shown in the UI
- [ ] Ticker/company test set: ~30 recorded questions with company names; baseline entity WER
- [ ] Custom vocabulary / keyword boosting + entity post-correction; WER after
- [ ] Voice settings per client (voice, speaking style) from Sprint 4's config
- [ ] Optional stretch: a phone number (Twilio) routed to the same pipeline
- [ ] ADR-0005: provider choice and latency findings

**Done when:** you can ask out loud for a company's latest revenue and get a spoken, sourced answer, with a measured before/after transcription accuracy on your ticker list.

**Explain it in 2 minutes:** where the latency went and what you did about it; how you tuned transcription for domain vocabulary, with numbers; how you'd debug a live voice agent a customer says "sounds dumb".

**Docs if stuck:** [Deepgram](https://developers.deepgram.com/) · [ElevenLabs](https://elevenlabs.io/docs) · [Twilio Voice](https://www.twilio.com/docs/voice) · [MDN MediaRecorder](https://developer.mozilla.org/docs/Web/API/MediaRecorder) · [FastAPI WebSockets](https://fastapi.tiangolo.com/advanced/websockets/)

---

### Sprint 6 — Observability and evals in CI (~10h)

**Objective:** see inside every conversation, and stop regressions from reaching `main`.

**Why it's interesting:** agents fail in ways unit tests don't catch. Tracing every step and running evals on every change is how you debug them and keep them from regressing.

**Background:**
- **Tracing:** each conversation is a trace; each LLM call, tool call, retrieval and STT/TTS step is a span with inputs, outputs, latency, tokens and cost. You debug agents by reading traces, not logs.
- **Evals as tests:** a fixed set of scenarios (questions + expected behaviour: right tool, right facts, citations present, no hallucinated numbers) run on every prompt or model change. A drop beyond a threshold fails CI.
- **Failure analysis:** collect real failures, classify them (retrieval miss, wrong tool, bad prompt, provider error), fix the class, add a regression case.

**Tech:** Langfuse (or OpenTelemetry), pytest-based eval runner, `claude-haiku-5-5` as judge, GitHub Actions.

**Tasks:**
- [ ] Instrument the agent, tools, retrieval and voice with Langfuse traces
- [ ] Cost and latency per conversation stored and shown in a "Traces" page in the dashboard
- [ ] `evals/agent.jsonl`: ~20 agent scenarios (tool choice, citations, refusal of trading advice, error handling)
- [ ] Eval runner producing a scored report; thresholds in config
- [ ] CI job running evals on PRs that touch prompts, tools or models (cached/cheap: Haiku judge, small set); fails on regression
- [ ] `docs/failure-log.md`: 5+ real failures found through traces, root cause, fix, regression case
- [ ] A small usage dashboard: questions per day, success rate, median latency, cost

**Done when:** a deliberately broken prompt change fails CI with a readable report of which evals regressed, and the failure log has at least 5 real entries.

**Explain it in 2 minutes:** a real bug you found from a trace; how your eval gate works and what it costs per run; how you'd monitor agents for a customer in production.

**Docs if stuck:** [Langfuse](https://langfuse.com/docs) · [OpenTelemetry](https://opentelemetry.io/docs/) · [Claude API docs](https://docs.anthropic.com/)

---

### Sprint 7 — Ship to AWS (~10h)

**Objective:** one merge deploys the whole stack to AWS; one command destroys or rebuilds it.

**Why it's interesting:** containers, deployment and infrastructure as code turn "works on my machine" into "works anywhere, and can be rebuilt from scratch". Also hands-on practice for AWS SAA-C03.

**Background:**
- **Containers:** multi-stage Dockerfiles for small images; one image for the API (and MCP server), static build for the frontend.
- **AWS pieces:** ECR (images), ECS Fargate (run containers without servers), RDS Postgres (managed DB with pgvector), S3 + CloudFront (frontend), Secrets Manager (keys), CloudWatch (logs), VPC/security groups (who can talk to whom).
- **Terraform:** declare the infrastructure as code; `plan` shows changes, `apply` creates, `destroy` removes. State stored remotely (S3) once it matters.
- **OIDC:** GitHub Actions assumes an AWS role with short-lived credentials; no access keys stored in GitHub.

**Tech:** Docker, Terraform, AWS (ECR, ECS Fargate, RDS, S3, CloudFront, Secrets Manager, CloudWatch), GitHub Actions OIDC.

**Tasks:**
- [ ] AWS Budgets alert at €20 (do this **first**)
- [ ] Harden the backend Dockerfile from Sprint 0 for production (ADR-0001); frontend production build
- [ ] `infra/terraform/`: VPC basics, ECR, RDS Postgres (smallest instance), ECS Fargate service, S3 + CloudFront, Secrets Manager, CloudWatch logs
- [ ] Enable pgvector on RDS; run Alembic migrations as a one-off task
- [ ] GitHub Actions: OIDC role; on merge to `main` build, push and deploy
- [ ] `make cloud-up` / `make cloud-down` wrapping `terraform apply` / `destroy`
- [ ] Smoke test after deploy (`/health`, one chat request)
- [ ] ADR-0006: deployment design and cost per day while up

**Done when:** merging a PR deploys automatically to a public URL, and `terraform destroy` followed by `terraform apply` rebuilds a working stack.

**Explain it in 2 minutes:** why Fargate over EC2/Lambda for this; how secrets reach the containers; OIDC vs access keys; what the stack costs and how you keep it down.

**Docs if stuck:** [Terraform](https://developer.hashicorp.com/terraform/docs) · [Terraform AWS provider](https://registry.terraform.io/providers/hashicorp/aws/latest/docs) · [Amazon ECS](https://docs.aws.amazon.com/ecs/) · [Amazon RDS](https://docs.aws.amazon.com/rds/) · [GitHub Actions OIDC with AWS](https://docs.github.com/actions/deployment/security-hardening-your-deployments/configuring-openid-connect-in-amazon-web-services) · [Docker multi-stage builds](https://docs.docker.com/build/building/multi-stage/)

---

### Sprint 8 — Second client, docs and demo (~6h)

**Objective:** prove the multi-client workflow, and package the project so a stranger gets it in minutes.

**Why it's interesting:** the real test of a platform is the second customer. Onboarding through config only, plus docs a stranger can follow, show whether the design holds up.

**Background:**
- **Onboarding as a product:** if a new client takes code changes, it doesn't scale. Everything client-specific (watchlist, prompt, tone, tools, voice, alerts) should be configuration.
- **Developer docs:** quickstart first (clone to first answer in 5 commands), then concepts, then reference. Show, don't tell: diagrams, screenshots, numbers.
- **Impact claims:** one honest, measured number beats adjectives.

**Tech:** everything above, plus a screen recorder.

**Tasks:**
- [ ] Onboard a second client (different watchlist, prompt, voice, Slack alert) through config only; **time it** (target < 30 min) and note what was painful
- [ ] Fix the worst onboarding pain point found
- [ ] README rewritten as an integration guide: pitch, 5-command quickstart, architecture diagram, eval/latency/WER numbers, cost, limitations, roadmap
- [ ] One measured impact claim (e.g. time to answer a research question manually vs with Market Desk, on 10 questions)
- [ ] 2-3 minute demo video aimed at a non-technical viewer (chat, voice, citations, onboarding)
- [ ] Pin the repo on GitHub; add the demo link to the README
- [ ] Final PROGRESS.md entry and a short retrospective (what you'd do differently)

**Done when:** a stranger can go from clone to first answer using only the README, and the demo video explains the product to a non-technical viewer.

**Explain it in 2 minutes:** the 2-minute walkthrough; onboarding time and what you fixed; the impact number and how you measured it.

**Docs if stuck:** your own docs. If they don't answer your question, they're not done yet.

---

## 9. Out of scope

**Deliberately not covered:** building knowledge graphs (Market Desk consumes Cala's graph instead), trading advice or real-time prices, mobile apps, production SLAs.

---

## 10. After the project

1. Write a retrospective: what worked, what I'd do differently, which numbers moved and why.
2. Prepare a 2-minute walkthrough and a 10-minute technical deep dive (architecture, agent loop, eval numbers, a bug from the failure log).
3. Decide what to build or learn next.
