# Shortcuts for the commands used every day. CI calls the same targets (lint, test),
# so the checks are defined once. Recipes work in cmd, PowerShell, Git Bash and Linux.
# Recipe lines MUST start with a tab, not spaces ("missing separator" error otherwise).

.DEFAULT_GOAL := help
.PHONY: help install up down dev test lint fmt

help:
	@echo Targets:
	@echo   make install  - install dependencies and the git pre-commit hook (fresh clone)
	@echo   make up       - build and start db, migrate and api in Docker (API on :8000)
	@echo   make down     - stop and remove the containers (the database volume is kept)
	@echo   make dev      - run the API locally with auto-reload (needs the db container)
	@echo   make test     - run the test suite (needs the db container)
	@echo   make lint     - check lint, formatting and types; never changes files (used by CI)
	@echo   make fmt      - format code and apply safe lint fixes (changes files)

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
