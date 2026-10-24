# Commands

The commands worth keeping, grouped by tool. This page is the only copy: add to it when a new command earns a place.

## Everyday (Makefile, from the repo root)
```bash
make install        # fresh clone: install dependencies and the pre-commit hook
make up             # build and start db, migrate and api in Docker (API on :8000)
make down           # stop and remove the containers (the database volume is kept)
make dev            # API locally with auto-reload (needs the db container)
make test           # test suite (needs the db container)
make lint           # lint, formatting and types; never changes files (CI runs this)
make fmt            # format and apply safe lint fixes (changes files)
make check          # lint, then tests: what CI checks
make docs-serve     # journal site with live reload: http://127.0.0.1:8001/market-desk/
make docs-build     # strict site build into site/ (fails on broken links/anchors)
```

## uv (from `backend/`)
```bash
uv sync                                              # create .venv from uv.lock
uv add <pkg> / uv add --dev <pkg>                    # add runtime / dev dependency
uv add --group docs <pkg>                            # add to a named group
uv run pytest -q                                     # run tests inside the venv
uv run --group docs mkdocs serve -f ../mkdocs.yml    # include a non-default group for one command
uv run uvicorn market_desk.api.main:app --reload     # dev server on :8000, docs at /docs
```

## pytest
```bash
uv run pytest tests/a.py::test_x tests/b.py::test_y  # run in this order: catches order-dependent tests
```

## Docker Compose (from the repo root)
```bash
docker compose up -d --build                      # after pulling backend changes: rebuild, or migrate fails on new revisions
docker compose up -d                                 # start the stack
docker compose up -d --build                         # rebuild the image first
docker compose ps                                    # status + health
docker compose ps -a                                 # include exited one-off containers (migrate)
docker compose logs <service>                        # runtime errors of one service
docker compose exec db psql -U market_desk           # SQL shell inside the container
docker compose stop db / start db                    # simulate an outage
docker compose down        # remove containers, keep data;  down -v also deletes the volume
```

## Alembic (from `backend/`)
```bash
uv run alembic upgrade head          # apply all migrations
uv run alembic downgrade -1          # undo the last one (downgrade base: undo all)
uv run alembic current               # revision the DB is at (the alembic_version row)
uv run alembic history               # the migration chain
uv run alembic revision -m "msg"     # new empty migration
uv run alembic revision --autogenerate -m "msg"   # diff models vs DB; always review the output
```

## GitHub CLI
```bash
gh pr checks <n> --watch                                       # wait for a PR's CI result
gh run view <run-id> --log-failed                              # only the failed steps' logs
gh api repos/<owner>/<repo>/git/matching-refs/tags/v10         # which tags an action really has
gh api repos/<owner>/<repo>/rulesets                            # list rulesets; add /<id> for one in full
gh api repos/<owner>/<repo>/commits/<sha>/check-runs            # check names and the app that reported them
gh api repos/<owner>/<repo>/pages                               # Pages config (build_type: workflow = GitHub Actions)
uvx --from actionlint-py actionlint .github/workflows/*.yml     # static check of workflow files
```

## pytest
```bash
uv run pytest tests/test_cala_retries.py -q            # one file, quiet
uv run pytest tests/test_cala_errors.py -q -k 422      # only tests whose name matches "422"
uv run pytest -q 2>&1 | grep -E "^E |FAILED"           # just the assertion lines and failed test names
```

## n8n (from the repo root)
```bash
make n8n-import                                   # JSON in n8n/workflows -> n8n, publish, restart
make n8n-export                                   # workflow edited in the UI -> n8n/workflows (cleaned)
docker compose exec n8n n8n list:workflow         # what n8n has
MSYS_NO_PATHCONV=1 docker compose exec n8n ls /n8n   # Git Bash: stop it rewriting /paths
cd backend && uv run python -m market_desk.webhooks.send_test   # send a signed sample event
```

## Watchlist and filing check (from `backend/`)
```bash
uv run python -m market_desk.watchlist add AAPL      # add + baseline (live EDGAR, no cache)
uv run python -m market_desk.watchlist list
uv run python -m market_desk.watchlist --client acme list   # another client (default: default)
uv run python -m market_desk.jobs.check_filings      # one check run; prints how many were announced
docker compose exec -T db psql -U market_desk -d market_desk -c "SELECT accession_number, notified_at FROM seen_filings;"
```

## Migrations against the test database (from `backend/`)
```bash
# Point Alembic at market_desk_test instead of the dev DB (its URL with the database swapped)
URL=$(uv run python -c "from sqlalchemy import make_url;from market_desk.config import Settings;print(make_url(Settings().database_url).set(database='market_desk_test').render_as_string(hide_password=False))")
DATABASE_URL="$URL" uv run alembic upgrade head
DATABASE_URL="$URL" uv run alembic check                                   # models == migrations?
DATABASE_URL="$URL" uv run alembic revision --autogenerate -m "message"    # new migration from the models
uv run alembic revision -m "message"                                       # empty file, to write by hand
```
