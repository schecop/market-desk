# syntax=docker/dockerfile:1

# ---------- Stage 1: build the virtualenv with uv ----------
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder

# Compile .pyc at build time (faster container start); copy files out of uv's cache
# instead of hard-linking (the cache is a separate mount); never download a Python,
# use the one in the image.
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0

WORKDIR /app

# 1) Dependencies only. This layer is rebuilt only when pyproject.toml or uv.lock change,
#    so code edits don't reinstall every package.
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-install-project --no-dev

# 2) The project itself. --no-editable installs it into site-packages, so the runtime
#    stage needs only .venv, not src/.
COPY . /app
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-editable


# ---------- Stage 2: minimal runtime image ----------
# Same Debian + Python as the builder, so the venv's interpreter links still resolve.
FROM python:3.12-slim-bookworm AS runtime

# Unprivileged user: a compromised app doesn't get root inside the container
RUN useradd --system --uid 1001 --no-create-home app

WORKDIR /app
COPY --from=builder --chown=app:app /app/.venv /app/.venv
# Alembic reads its settings from these two files in the working directory
COPY --chown=app:app pyproject.toml alembic.ini ./

# Use the venv's python, uvicorn and alembic without activating it; print logs immediately
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1

USER app
EXPOSE 8000

# Exec form: uvicorn is PID 1 and receives SIGTERM directly, so `docker stop` is graceful
CMD ["uvicorn", "market_desk.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
