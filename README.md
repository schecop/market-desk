# Market Desk

[![CI](https://github.com/schecop/market-desk/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/schecop/market-desk/actions/workflows/ci.yml)
[![Docs](https://github.com/schecop/market-desk/actions/workflows/docs.yml/badge.svg?branch=main)](https://github.com/schecop/market-desk/actions/workflows/docs.yml)

**An AI research desk for public companies, over chat and voice.** Ask about any listed company and get answers grounded in verified facts ([Cala](https://www.cala.ai/)'s knowledge graph) and SEC filings, with citations. Built as a multi-client agent platform: a hand-written tool-use agent on the Claude API, hybrid RAG with measured evals, an MCP server, a React + TypeScript dashboard, a voice channel, tracing, and an AWS deployment with Terraform.

> **Status:** Sprint 0 (scaffold) complete; next up, Sprint 1 (integrations). Nine sprints, 0 to 8. Built in public: session log in [`PROGRESS.md`](PROGRESS.md), and what was built, why, and what was learned in the **[learning journal](https://schecop.github.io/market-desk/)**.

## Quick start
Needs [Docker](https://docs.docker.com/get-docker/), [uv](https://docs.astral.sh/uv/) and GNU make (on Windows: `winget install ezwinports.make`).

```bash
cp .env.example .env   # local settings; the Sprint 0 defaults work as-is
make install           # Python dependencies + the pre-commit hook
make up                # Postgres, migrations and the API in Docker
make check             # lint, types and tests: what CI runs
```

The API answers at http://localhost:8000/health (interactive docs at `/docs`). `make help` lists every command; `make docs-serve` previews the journal at http://127.0.0.1:8001/market-desk/.

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
