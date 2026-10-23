---
tags:
  - integrations
  - automation
  - security
---

# 6. n8n and Slack

**Sprint 1** · **Date:** 2026-10-23 · **Plan item:** n8n in Docker Compose; a flow that receives "new 10-K filed for a watchlist company" and posts to Slack

## What and why
n8n runs next to the API in Docker Compose. One workflow receives our signed events (task 5's dispatcher), verifies the Standard Webhooks signature itself, answers 202 or 401, and posts `filing.created` events to a Slack channel. Our code only promises a signed event; what happens next (Slack today, email or a CRM tomorrow) is changed in n8n without touching the backend. Task 7 sends the real events.

## Decisions
| Date | Decision | Why | Alternatives considered | ADR |
|---|---|---|---|---|
| 2026-10-23 | Pin `n8nio/n8n:2.44.6` (the `stable` tag that day) | `latest` moves weekly; an upgrade should be a reviewed change, not a surprise on `docker compose pull` | `latest` or `stable` tags | |
| 2026-10-23 | Verify the signature in a **Code node** (Node's `crypto`), on the raw body | Standard Webhooks needs the `whsec_` key base64-decoded and `id.timestamp.body` signed; a check on re-serialized JSON can differ by a byte | The Crypto node (can't decode the key or build the content cleanly); the Webhook node's header auth (a shared token: no tamper or replay protection) | |
| 2026-10-23 | Answer 401 / 202 from the workflow (Respond to Webhook nodes), before posting to Slack | Mirrors our inbound endpoint: the sender learns at once if it's refused, and a slow Slack never makes it retry | Respond immediately with 200 (a bad signature would look delivered) | |
| 2026-10-23 | Retry the Slack step in n8n (3 tries, 2 s apart) | We've already answered 202, so the sender won't retry; the receiver owns delivery from here | No retry (a Slack hiccup loses the message silently) | |
| 2026-10-23 | Workflows as JSON in the repo; `make n8n-import` / `make n8n-export`, with a cleaner for exports | Reviewable and reproducible; the n8n database is only a working copy | Build only in the UI (lost with the volume, invisible in PRs) | |
| 2026-10-23 | Pass only `WEBHOOK_SIGNING_SECRET` and `SLACK_WEBHOOK_URL` to n8n, read with `$env` | Least privilege: n8n doesn't need the Cala or Anthropic keys | `env_file: .env` (every secret in one more container); n8n credentials (stored in its DB, not reproducible from the repo) | |

## Concepts
### Low-code automation as an integration layer
Tools like n8n, Zapier or Make connect systems with visual workflows: a trigger (a webhook, a schedule), then steps (filter, transform, call an API). The contract between our backend and n8n is just the signed event; operations people can change what happens after it without a deploy. The trade-off: logic in n8n isn't covered by our tests, so keep it thin (route and format), and keep business rules in code.

### Docker network names vs `localhost`
Inside a container, `localhost` is the container itself. Compose puts services on one network where each is reachable by its service name: the API container would call `http://n8n:5678`, while your machine (uvicorn, the `send_test` command) uses `http://localhost:5678` through the published port.

### n8n test URL vs production URL, and publishing
A Webhook node has two URLs. `/webhook-test/...` works only while the editor is listening ("Execute workflow") and shows each node's data on the canvas, which is good for debugging. `/webhook/...` works only once the workflow is **published** (active), and its runs appear under Executions. A published workflow changed from the CLI only takes effect after a restart.

### Raw body vs parsed body
A signature covers bytes. n8n parses JSON bodies into `$json.body`; `JSON.stringify` of that can differ from what was sent (spacing, key order, escaped `/`), so the HMAC wouldn't match. The Webhook node's **Raw Body** option keeps the exact bytes as binary data, read with `this.helpers.getBinaryDataBuffer(0, 'data')`.

## Code map
| File | What it does | Why it exists / why this way |
|---|---|---|
| `docker-compose.yml` | `n8n` service: pinned image, port 5678, `n8n_data` volume, `./n8n` mounted at `/n8n`, two secrets passed from `.env` | `NODE_FUNCTION_ALLOW_BUILTIN=crypto` and `N8N_BLOCK_ENV_ACCESS_IN_NODE=false` let the Code node verify signatures |
| `n8n/workflows/new-10k-to-slack.json` | Webhook (raw body) → Verify signature → Valid? → 202 or 401 → New filing? → Post to Slack | The workflow as code |
| `n8n/scripts/clean-export.js` | Keeps `id`, `name`, `nodes`, `connections`, `settings` from an n8n export | Exports carry timestamps, version ids and the owner project: churn in every diff |
| `n8n/README.md` | The import/edit/export loop, URLs, secrets, how to try it | |
| `Makefile` | `n8n-import` (import, publish, restart) and `n8n-export` (export, clean) | Paths inside one `sh -c` string, so Git Bash doesn't rewrite them |
| `backend/src/market_desk/webhooks/send_test.py` | `python -m market_desk.webhooks.send_test [type]`: sends a sample event with `WebhookDispatcher` | Proves the flow end to end before task 7 sends real events; defines the `filing.created` data shape |
| `.env.example` | `N8N_WEBHOOK_URL` default, `SLACK_WEBHOOK_URL` explained | |

## Gotchas
!!! bug "Git Bash rewrote a container path into a Windows path"
    **Symptom:** `docker compose exec n8n n8n import:workflow --input=/tmp/probe.json` failed with `ENOENT: ... open 'C:/Users/pablo/AppData/Local/Temp/probe.json'`.
    **Cause:** Git Bash (MSYS) converts arguments that look like Unix paths into Windows paths before running a Windows program like `docker.exe`; it can't know the path is meant for inside a container.
    **Fix:** `MSYS_NO_PATHCONV=1` for one-off commands; in the Makefile, the paths sit inside one quoted `sh -c "..."` string, which isn't converted.
    **Lesson:** when a path works in PowerShell but not in Git Bash, suspect MSYS path conversion.

!!! bug "`import:workflow --activeState=fromJson` refused to activate"
    **Symptom:** "can only be used when n8n is running in queue or multi-main mode".
    **Cause:** n8n 2.x replaced "activate" with **publish**; a single-instance setup publishes with a separate command.
    **Fix:** `n8n import:workflow` then `n8n publish:workflow --id=...`, then restart n8n.
    **Lesson:** check the CLI's `--help` for the version you run; tutorials often describe 1.x.

!!! bug "Slack step failed with `invalid syntax`, after a 202"
    **Symptom:** the sender got 202, but the Slack node failed 3 times with `invalid syntax`; nothing was posted. Hidden at first because an empty Slack URL failed earlier, before the expression ran.
    **Cause:** the body expression is JavaScript stored inside JSON. `"...'\n<'..."` in the JSON file is a **real line break** once parsed, and a raw line break isn't allowed inside a `'...'` JS string.
    **Fix:** `\\n` in the JSON file, which reaches JavaScript as the two characters `\n`, an escape it turns into a newline.
    **Lesson:** code inside a string inside another format has two layers of escaping; count them. And test each step with real inputs: a failure upstream can hide one downstream.

## Check questions
??? question "When the backend runs inside the `api` container (task 7), what must `N8N_WEBHOOK_URL` be, and why does `localhost:5678` fail there?"
    `http://n8n:5678/webhook/market-desk`. Inside a container, `localhost` is **that container**: from `api`, port 5678 has nothing listening, so it's "connection refused" even on a laptop. Compose services reach each other by service name (`n8n`, `db`). In AWS, neither applies: it's the deployed n8n's URL. *(My first answer blamed local vs production; the real reason is that each container has its own `localhost`.)*

??? question "What if the Verify node signed `JSON.stringify($json.body)` instead of the raw bytes?"
    With today's compact `model_dump_json()` it would likely pass, **by luck**, and break on ordinary differences: `1.0` parsed by JS and re-serialized as `1`; a sender that adds spaces (`json.dumps` default, pretty-printing); JS moving integer-like keys (`"10"`) to the front. A signature covers bytes, not "the same data": verify the bytes received, then parse.


## Guided exercise
**Task (complete code left with `TODO` markers):** write the "Verify signature" Code node in JavaScript: the same Standard Webhooks check as `verified_event` in Python. Edit it in the n8n UI, then `make n8n-export`.

**Outcome:** I asked Claude to write the Code node. In its place, a **break-it-on-purpose** exercise: remove `.replace(/^whsec_/, '')`, predict, run `send_test`, restore with `make n8n-import`. Predicted and got **401 `bad signature`**. Then a `filing.created` sample reached Slack.

**What I got wrong:** I didn't know why the length check comes before `crypto.timingSafeEqual`: it **throws** on buffers of different lengths, so a junk `v1,AAAA` would become a 500 and the dispatcher would retry it. Checking the length first makes it a clean 401, and leaks nothing (every valid signature is 32 bytes).

**Lesson:** Node's base64 decoder is lenient: `whsec_...` decodes **silently** to a different key, so a key-format mismatch looks exactly like a forged request. And the repo is the source of truth: `make n8n-import` restores a broken workflow faster than fixing it in the UI.

## Explain it in 2 minutes
Our backend publishes events; n8n decides what to do with them. n8n runs in Docker Compose, pinned to a version, with only the two secrets it needs. A workflow receives our Standard Webhooks events on its production URL, keeps the raw body (a signature covers bytes, and re-serialized JSON can differ), and verifies the signature in a Code node the same way our Python endpoint does: the `whsec_` key decoded, an HMAC of id, timestamp and body, a five-minute window, a length check, then a constant-time comparison. A bad request gets a 401, so the sender knows at once; a good one gets a 202 straight away, and only then does the workflow route `filing.created` events to Slack, retrying that step itself, since the sender is already done. The workflow lives in the repo as JSON: `make n8n-import` loads and publishes it, `make n8n-export` writes UI edits back, cleaned of instance noise, so changes are reviewed in pull requests. The rule for what goes where: n8n routes and formats, business logic stays in tested Python code.
