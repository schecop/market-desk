---
tags:
  - docker
---

# 4. Dockerfile and the containerised stack

**Sprint 0** · **Date:** 2026-10-11 → 2026-10-13 · **Plan item:** Multi-stage `Dockerfile` (uv) for the API + `api` service in `docker-compose.yml`; runs migrations on start ([ADR-0001](../../adr/0001-containerise-api-in-sprint-0.md))

## What and why
A multi-stage Dockerfile builds the API image: a uv stage makes the virtualenv, a slim non-root stage runs it. Compose now starts the whole stack in order: `db`, then a one-off `migrate`, then `api`. It was moved forward from Sprint 7 so container problems show up while the app is tiny.

## Decisions
| Date | Decision | Why | Alternatives considered | ADR |
|---|---|---|---|---|
| 2026-10-11 | Dockerfile + `api` Compose service in Sprint 0 (moved forward from Sprint 7), right after Alembic | Makes "Done when" true; container issues surface while the app is tiny; one command starts the whole stack | Keep it in Sprint 7 and reword "Done when" | [ADR-0001](../../adr/0001-containerise-api-in-sprint-0.md) |
| 2026-10-12 | Multi-stage Dockerfile: uv image builds `.venv`, `python:3.12-slim-bookworm` runs it | Small runtime image without uv or build tools; deps layer cached separately from code | Single stage; `alpine` (musl breaks many wheels); `pip install` (ignores `uv.lock`) | [ADR-0001](../../adr/0001-containerise-api-in-sprint-0.md) |
| 2026-10-12 | Separate one-off `migrate` Compose service; `api` waits for it to exit 0 | No race between API replicas running migrations; mirrors the one-off ECS task in Sprint 7; API never starts on an unexpected schema | `alembic upgrade head && uvicorn ...` in the API's start command | — |
| 2026-10-12 | `script_location` in package notation (`market_desk:db:migrations`) | Image has no `src/`, only site-packages; one setting works locally, in tests and in the container | Filesystem path + copy `src/` into the image | — |
| 2026-10-12 | Project installed `--no-editable` in the image | Runtime stage needs only `.venv` | Editable install + copy `src/` | — |

## Concepts

### Image vs container
An *image* is the built, read-only template (`docker build`); a *container* is a running instance of it (`docker run`, `compose up`). One image, many containers: `migrate` and `api` run the same image with different commands. Build-time problems show in the build output; runtime problems in `docker compose logs <service>`.

### Layer caching
Each Dockerfile instruction makes a layer. Docker reuses a layer if the instruction **and its inputs** are unchanged; once one layer is rebuilt, **every layer after it is rebuilt too**. So put what changes rarely first: dependency manifests (`pyproject.toml`, `uv.lock`) and install, *then* `COPY` the code. With `COPY . /app` first, any code edit reinstalls every dependency. Read the `CACHED` markers in the build output, not just the time.

### Multi-stage builds
Several `FROM`s in one Dockerfile. Earlier stages build things (with compilers, uv, caches); the final stage copies only the result (`COPY --from=builder`). Smaller image, faster pulls (ECS in Sprint 7), smaller attack surface. Builder and runtime must share OS and Python path, because a venv's `python` is a link to the system interpreter.

### BuildKit mounts
`--mount=type=bind` makes a file visible during one `RUN` only (not stored in a layer); `--mount=type=cache` keeps a directory (uv's download cache) between builds.

### Container hardening basics
Non-root `USER`; `.dockerignore` keeps `.env` out (a secret copied into a layer stays in the image forever, even if deleted later); `--host 0.0.0.0` because `127.0.0.1` inside a container only accepts connections from inside it; exec-form `CMD ["uvicorn", ...]` so the app is PID 1 and gets `SIGTERM` (graceful stop in ~1s; shell form would wait 10s and then get killed).

### Compose networking
Services share a network where each **service name is a hostname** (`db`). Inside a container, `localhost` is that container. `ports: "5432:5432"` is only for the host (your laptop) to reach a container.

### `depends_on` conditions
`service_healthy` waits for the healthcheck; `service_completed_successfully` waits for a one-off container to exit with code 0. If `migrate` fails, `api` never starts.

### YAML anchors
`x-backend: &backend` names a block; `<<: *backend` merges it into a service. Shared config written once.

## Code map
| File | What it does | Why it exists / why this way |
|---|---|---|
| `backend/Dockerfile` | Multi-stage build: uv builder makes `.venv`, slim non-root runtime runs uvicorn | Same artefact locally, in CI and on ECS (Sprint 7) |
| `backend/.dockerignore` | Keeps `.venv`, caches, tests and `.env` out of the build context | Smaller context, no secrets in images |
| `docker-compose.yml` | `db` (Postgres 16 + pgvector), one-off `migrate`, `api` on :8000; shared `x-backend` anchor | `docker compose up -d --build` starts the whole stack in order |

## Gotchas
!!! bug "(exercise) `migrate` exits non-zero with `Connection refused`; `api` never starts"
    **Cause:** `DATABASE_URL` host `localhost`: inside a container that's the container itself.
    **Fix:** host = service name `db`.
    **Lesson:** containers reach each other by service name; `ports:` is for the host only.

## Check questions
!!! note "Reconstructed"
    These questions were written during the journal migration, from what this task covered; the originals weren't recorded.

??? question "You change one line in `api/main.py` and rebuild. Which steps show `CACHED`, and which rerun?"
    Everything up to and including the dependency install stays cached, because `pyproject.toml` and `uv.lock` didn't change. The `COPY` of the code and every step after it rerun. If the code were copied before the install, every code edit would reinstall all dependencies.

??? question "Why run migrations in a separate `migrate` service instead of `alembic upgrade head && uvicorn ...` in the API's command?"
    With several API replicas, each would try to migrate at the same time (a race). A one-off job runs once, and `api` only starts if it exited 0, so the API never runs against an unexpected schema. It's the same shape as the one-off ECS task in Sprint 7.

??? question "You add `.env` to the image by mistake, then delete it in a later `RUN rm .env`. Is the secret gone?"
    No. Each instruction is a layer, and the layer that copied `.env` is still in the image; anyone who pulls it can extract it. Keep secrets out of the build context with `.dockerignore`.

??? question "Why does uvicorn need `--host 0.0.0.0` in the container?"
    `127.0.0.1` inside a container means the container itself, so it would only accept connections from inside it; the published port from your laptop would get nothing. `0.0.0.0` listens on all the container's interfaces.

## Guided exercise
**Task (type):** A: move `COPY . /app` above the deps install, predict and observe which steps rerun (break on purpose). B: `localhost` instead of `db` in `DATABASE_URL`, predict and diagnose from `ps -a` and the logs.

**Outcome:** done (2026-10-13): predictions right; stack restored, `/health` 200, 6 tests pass.

**What I got wrong:** said "build crashed" / "api image constructed" for runtime events (image vs container); in A, only noted that the next step lost its cache, not every later one.

**Lesson:** order layers by change frequency; image (build) vs container (run); `localhost` in a container is the container.

## Explain it in 2 minutes
The API ships as a Docker image built in two stages: the first uses uv to build the virtualenv from the lockfile, the second is a slim Python image that only gets that virtualenv and runs as a non-root user. Dependencies are installed before the code is copied, so a code change reuses the cached dependency layer and rebuilds in seconds. Compose starts the database, waits for its healthcheck, runs migrations as a one-off container, and only starts the API if migrations exited cleanly, which is how it will work on ECS too. Containers find each other by service name, never `localhost`, and secrets stay out of the image with `.dockerignore`.
