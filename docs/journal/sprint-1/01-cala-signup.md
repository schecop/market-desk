---
tags:
  - config
  - security
---

# 1. Cala sign-up and API key

**Sprint 1** · **Date:** 2026-10-16 · **Plan item:** Sign up for Cala's free tier; read its API docs; store the key in `.env`

## What and why
Signed up for Cala's free tier, read the API docs, and stored the key in `.env` (gitignored). `Settings` now exposes it as `cala_api_key`, masked, so the client in task 2 can read it from one place.

## Decisions
| Date | Decision | Why | Alternatives considered | ADR |
|---|---|---|---|---|
| 2026-10-16 | `cala_api_key: SecretStr \| None = None` | Masked in repr, logs and tracebacks; optional so the app and CI start without a key (CI never calls live APIs) | Plain `str` (leaks in logs); required field (breaks CI and any key-less run); reading `os.environ` directly (scattered, unvalidated) | |
| 2026-10-16 | Name the key `market-desk-dev` in Cala's dashboard | One key per environment: revoke or rotate one without breaking the other (`market-desk-prod` comes in Sprint 7) | One shared key for everything | |

## What the Cala API looks like
From the docs and the OpenAPI spec (`https://api.cala.ai/openapi.json`; fetched without a key, so it costs no calls).

- **Base URL:** `https://api.cala.ai` · **Auth:** API key in the `X-API-KEY` header
- **Free tier:** 100 calls in total

| Method | Path | What it returns | Paging |
|---|---|---|---|
| `POST` | `/v1/knowledge/search` | Natural-language answer with sources; body `{input, explainability, return_entities}` | none |
| `POST` | `/v1/knowledge/query` | Structured rows (`results: [ {...} ]`, shape depends on the query); body `{input, return_entities}` | none |
| `GET` | `/v1/entities?name=&entity_types=&limit=` | Entities by name, most relevant first | `limit` only (1-100, default 20), no offset or cursor |
| `POST` | `/v1/entities/{entity_id}` | One entity; optional body picks properties and relationships | `limit` + `offset` **per relationship type** |
| `GET` | `/v1/entities/{entity_id}/introspection` | Which properties and relationships an entity has | none |

**Errors** (every endpoint documents only `200`, `422`, `429`):

- `422`: `{"response_type": "ERROR", "error": {"error_type": "...", "message": "..."}}`. `error_type` is an enum: `format_error`, `entity_not_found_error`, `search_query_error`, `internal_server_error`, `service_unavailable_error`, `bad_gateway_error`, ...
- `429`: a **different shape**, `{"error": "rate_limit_exceeded", "message": "..."}`. No `Retry-After` is documented.

## Concepts
### Field validators: `before` vs `after`
`@field_validator("field", mode="before")` runs on the **raw input** (here the string from the environment), before Pydantic converts it to the field's type. `mode="after"` runs on the already-converted value. To turn `""` into `None` you need `before`: by `after`, the value is already `SecretStr('')`.
```python
@field_validator("cala_api_key", mode="before")
@classmethod
def empty_string_to_none(cls, v: Any) -> Any:
    if isinstance(v, str) and not v.strip():
        return None
    return v
```

### Type narrowing
mypy tracks what a value *can* be. After `key: SecretStr | None`, calling `key.get_secret_value()` is an error, because `key` might be `None`. A check such as `assert key is not None` or `if key is None: raise ...` **narrows** the type, and from that line on mypy knows it's a `SecretStr`. In tests, it's often simpler to compare against the literal you put in.

### `SecretStr`
A Pydantic type for secrets. `repr()` and `str()` show `'**********'` instead of the value, so a logged settings object or a traceback doesn't leak the key. Reading the real value takes a deliberate `.get_secret_value()`, which makes every place that touches the secret easy to find with a search.
```python
key = SecretStr("abc123")
print(key)                     # **********
key.get_secret_value()         # 'abc123'
```

### One key per environment
Name keys after where they're used (`market-desk-dev`, `market-desk-prod`). If one leaks you revoke only that one, and the name tells you where it leaked from.

### Reading an OpenAPI spec
An OpenAPI spec (`openapi.json`) is the machine-readable contract of an HTTP API: paths, methods, parameters, request and response schemas, auth schemes. Human docs summarise it and sometimes leave things out. The spec is where you find details like "retrieving an entity is a `POST`" or "the 429 body has a different shape". Many APIs serve it publicly; FastAPI generates ours at `/openapi.json`.

## Code map
| File | What it does | Why it exists / why this way |
|---|---|---|
| `backend/src/market_desk/config.py` | Adds `cala_api_key: SecretStr \| None` and a `before` validator turning empty or blank values into `None` | One typed place for config; masked secret; "set but empty" means "not set" |
| `backend/tests/test_config.py` | Tests: empty key → `None`; a fake key never appears in `repr`/`str` of the settings | Locks in both behaviours the client will rely on |
| `.env` (not committed) | Holds the real key | Gitignored (`.gitignore:2`); `.env.example` already lists `CALA_API_KEY` |

## Gotchas
!!! bug "The key loaded but had length 0"
    **Symptom:** `Settings().cala_api_key` was not `None`, but `.get_secret_value()` had length 0, and `repr` showed `SecretStr('')`.
    **Cause:** `CALA_API_KEY=` with nothing after it is an empty string, not a missing variable. Pydantic turns it into `SecretStr('')`, not `None`. It only masks non-empty values, so the repr showed `''`.
    **Fix:** put the key in `.env` and save the file. The client must treat empty as missing, not just check `is None`.
    **Lesson:** "set but empty" and "not set" are different states. Check for both whenever config is optional.

!!! bug "Two error shapes in one API"
    **Symptom:** (found while reading the spec) a `422` body has `error` as an object (`{error_type, message}`), and a `429` body has `error` as a string.
    **Cause:** different layers of Cala produce them, probably the app and the rate limiter in front of it.
    **Fix:** (task 2) the client parses errors defensively and maps them by **status code** first, not by body shape.
    **Lesson:** don't assume one error format per API. Read the spec for every status code.

## Check questions
??? question "Cala returns a `422` and a `429`. Which do you retry, and why?"
    Retry the `429`, with backoff, never the `422`. A `422` is a **client** error (4xx: the request failed validation), not a server error, so the same request always gets the same answer. `5xx` are the server errors, and they're usually worth retrying. Cala adds a caveat: if the `429` means the 100-call quota is spent, retrying doesn't help either. A `Retry-After` header, if present, hints at which one it is.

??? question "In CI `CALA_API_KEY` isn't set. What is `Settings().cala_api_key`? And with `CALA_API_KEY: \"\"`?"
    Unset: `None` (the default). Set to `""`: originally `SecretStr('')`, which would send an empty `X-API-KEY` header and get a confusing auth error. After this task's exercise, also `None`.

## Guided exercise
**Task (write the missing test, then fix the bug):** an empty `CALA_API_KEY` must count as "not configured" (`None`), and a key must never appear in `repr`/`str` of the settings. Acceptance: two tests, red first, then a fix in `config.py`, and `make check` green.

**Outcome:** done. A `mode="before"` `field_validator` maps empty or blank strings to `None`. Tests use `monkeypatch.setenv` (env vars win over `.env`, so the real key never interferes).

**What I got wrong:** the first version passed pytest but failed mypy strict: the validator had no type annotations, and the test called `.get_secret_value()` on a `SecretStr | None`. The leak test also joined two checks with `and` in one `assert`, so a failure wouldn't say which half failed.

**Lesson:** "tests pass" isn't "done": `make check` is. Compare against the literal you put in, rather than the value that came out. One `assert` per claim.

## Explain it in 2 minutes
The Cala key lives in `.env`, which Git ignores, and reaches the code through one typed `Settings` class. It's a `SecretStr`, so logging the settings or hitting a traceback shows asterisks, not the key. It's optional, so CI and any key-less run still start; the client will fail clearly when it actually needs the key. An empty value counts as missing, because "set but empty" would otherwise send a blank header. Before writing the client I read Cala's OpenAPI spec, not just the docs: it showed there's no cursor pagination, that retrieving an entity is a `POST`, and that `422` and `429` bodies have different shapes. That changes how the client maps errors. With only 100 calls on the free tier, tests always mock Cala.
