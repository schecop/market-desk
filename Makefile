# Shortcuts for the commands used every day. CI calls the same targets (lint, test),
# so the checks are defined once. Recipes work in cmd, PowerShell, Git Bash and Linux.
# Recipe lines MUST start with a tab, not spaces ("missing separator" error otherwise).
# make runs recipes in cmd from PowerShell but in sh from Git Bash and Linux, so the echo text
# below stays plain: no ( ) ; & | < > or quotes, which one of the two shells would misread.

.DEFAULT_GOAL := help
.PHONY: help install up down dev test lint fmt check docs-serve docs-build

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
