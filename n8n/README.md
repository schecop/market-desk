# n8n workflows

n8n runs in Docker Compose (`docker compose up -d n8n`, UI at <http://localhost:5678>). Workflows live
here as JSON, so they're reviewed and versioned like code; the n8n database is only a working copy.

| File | What it does |
|---|---|
| `workflows/new-10k-to-slack.json` | Receives our signed events, checks the Standard Webhooks signature, answers 202 or 401, and posts `filing.created` events to Slack |
| `scripts/clean-export.js` | Strips instance-specific fields from an n8n export, so the JSON diffs cleanly |

## The loop
```bash
make n8n-import      # load the JSON into n8n, publish it, restart n8n
# ...edit the workflow in the UI (first visit: create a local owner account), save...
make n8n-export      # write it back to workflows/, then review it with git diff
```

A published workflow answers on its **production URL**, `http://localhost:5678/webhook/market-desk`
(`N8N_WEBHOOK_URL` in `.env`). The **test URL** (`/webhook-test/...`) only works while the editor is
listening ("Execute workflow"), and shows the data on the canvas: handy for debugging a node.

## Secrets
The workflow reads `WEBHOOK_SIGNING_SECRET` and `SLACK_WEBHOOK_URL` with `$env`. Compose passes
only those two from `.env` to the container; they never appear in the JSON.

## Try it
```bash
cd backend
uv run python -m market_desk.webhooks.send_test              # a sample filing.created: posts to Slack
uv run python -m market_desk.webhooks.send_test test.ping    # accepted, nothing posted
```
Executions (including failed Slack posts) are in the UI under **Executions**.
