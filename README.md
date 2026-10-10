# Market Desk

**An AI research desk for public companies, over chat and voice.** Ask about any listed company and get answers grounded in verified facts ([Cala](https://www.cala.ai/)'s knowledge graph) and SEC filings, with citations. Built as a multi-client agent platform: a hand-written tool-use agent on the Claude API, hybrid RAG with measured evals, an MCP server, a React + TypeScript dashboard, a voice channel, tracing, and an AWS deployment with Terraform.

> **Status:** Sprint 0 of 8, just started. Built in public; follow along in [`PROGRESS.md`](PROGRESS.md).

## Roadmap
| Sprint | Focus |
|---|---|
| 0 | Scaffold: FastAPI, Postgres + pgvector, CI |
| 1 | Integrations: typed Cala and SEC EDGAR clients, webhooks, n8n |
| 2 | Agent core: hand-written tool-use loop, LangGraph variant, MCP server |
| 3 | RAG over filings with evaluation (naive → hybrid → reranked) |
| 4 | React + TypeScript dashboard |
| 5 | Voice channel with latency and transcription tuning |
| 6 | Observability and evals in CI |
| 7 | AWS deployment with Terraform and GitHub Actions |
| 8 | Multi-client onboarding, docs and demo |

The full plan (architecture, stack, sprint checklists) is in [`docs/PLAN.md`](docs/PLAN.md).

## Disclaimer
Market Desk is a research and learning project. It does not provide investment advice.

## License
MIT
