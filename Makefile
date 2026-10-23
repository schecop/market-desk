# Shortcuts for the commands used every day. CI calls the same targets (lint, test),
# so the checks are defined once. Recipes work in cmd, PowerShell, Git Bash and Linux.
# Recipe lines MUST start with a tab, not spaces ("missing separator" error otherwise).
# make runs recipes in cmd from PowerShell but in sh from Git Bash and Linux, so the echo text
# below stays plain: no ( ) ; & | < > or quotes, which one of the two shells would misread.

.DEFAULT_GOAL := help
.PHONY: help install up down dev test lint fmt check docs-serve docs-build n8n-import n8n-export

help:
	@echo Targets:
	@echo   make install    - fresh clone: install dependencies and the git pre-commit hook
	@echo   make up         - build and start db, migrate and api in Docker, API on port 8000
	@echo   make down       - stop and remove the containers, keeping the database volume
	@echo   make dev        - run the API locally with auto-reload, needs the db container
	@echo   make test       - run the test suite, needs the db container
	@echo   make lint       - check lint, formatting and types, never changes files - used by CI
	@echo   make fmt        - format code and apply safe lint fixes - changes files
	@echo   make check      - lint, then tests: what CI checks
	@echo   make docs-serve - preview the journal site with live reload: http://127.0.0.1:8001/market-desk/
	@echo   make docs-build - build the site into site/, failing on any warning - used by CI
	@echo   make n8n-import - load n8n/workflows into n8n, publish it and restart n8n
	@echo   make n8n-export - save the workflow edited in the n8n UI back to n8n/workflows

install:
	cd backend && uv sync
	cd backend && uv run pre-commit install

up:
	docker compose up -d --build

down:
	docker compose down

dev:
	cd backend && uv run uvicorn market_desk.api.main:app --reload

test:
	cd backend && uv run pytest

lint:
	cd backend && uv run ruff check .
	cd backend && uv run ruff format --check .
	cd backend && uv run mypy

fmt:
	cd backend && uv run ruff format .
	cd backend && uv run ruff check --fix .

# Prerequisites run first, left to right: lint, then test. No recipe of its own.
check: lint test

# The docs group is not installed by default (`uv sync` skips it), so ask for it explicitly.
# -f points at the repo-root config; MkDocs resolves docs_dir relative to that file.
# Port 8001 because the API container already holds 8000.
docs-serve:
	cd backend && uv run --group docs mkdocs serve -f ../mkdocs.yml -a 127.0.0.1:8001

# --strict turns warnings (broken links, pages missing from nav) into a failed build
docs-build:
	cd backend && uv run --group docs mkdocs build --strict -f ../mkdocs.yml

# n8n workflows live in the repo as JSON (n8n/README.md). The paths sit inside one quoted
# sh -c string so Git Bash doesn't rewrite /n8n into a Windows path.
# A published workflow only picks up changes after a restart.
N8N_WORKFLOW_ID := marketDesk10kSlk
N8N_WORKFLOW_FILE := /n8n/workflows/new-10k-to-slack.json

n8n-import:
	docker compose exec n8n sh -c "n8n import:workflow --input=$(N8N_WORKFLOW_FILE) && n8n publish:workflow --id=$(N8N_WORKFLOW_ID)"
	docker compose restart n8n

n8n-export:
# The raw export is noisy (timestamps, version ids, owner); clean-export.js keeps the definition.
	docker compose exec n8n sh -c "n8n export:workflow --id=$(N8N_WORKFLOW_ID) --output=/tmp/export.json && node /n8n/scripts/clean-export.js /tmp/export.json $(N8N_WORKFLOW_FILE)"
