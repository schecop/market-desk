# Concepts

Every concept from every task, one line each, linking to where it's explained. Use it to review: read the name, explain it in your head, then click to check.

<!-- Add one line per new concept: [Heading](../sprint-N/NN-page.md#anchor) · *Task title*.
     The anchor is the heading in lowercase, punctuation removed, spaces as hyphens; `make docs-build` fails if it's wrong. -->

## Sprint 0 — Scaffold
- [`pyproject.toml`](../sprint-0/01-package-and-health.md#pyprojecttoml) · *1. Package and health endpoint*
- [`uv.lock`](../sprint-0/01-package-and-health.md#uvlock) · *1. Package and health endpoint*
- [`src/` layout](../sprint-0/01-package-and-health.md#src-layout) · *1. Package and health endpoint*
- [Why `src/` prevents "works on my machine"](../sprint-0/01-package-and-health.md#why-src-prevents-works-on-my-machine) · *1. Package and health endpoint*
- [`uv run` auto-syncs](../sprint-0/01-package-and-health.md#uv-run-auto-syncs) · *1. Package and health endpoint*
- [ASGI, uvicorn and FastAPI](../sprint-0/01-package-and-health.md#asgi-uvicorn-and-fastapi) · *1. Package and health endpoint*
- [Return type annotations in FastAPI](../sprint-0/01-package-and-health.md#return-type-annotations-in-fastapi) · *1. Package and health endpoint*
- [`TestClient`](../sprint-0/01-package-and-health.md#testclient) · *1. Package and health endpoint*
- [Liveness vs readiness](../sprint-0/02-postgres-and-readiness.md#liveness-vs-readiness) · *2. Postgres and a readiness check*
- [Docker Compose basics](../sprint-0/02-postgres-and-readiness.md#docker-compose-basics) · *2. Postgres and a readiness check*
- [Engine and connection pool](../sprint-0/02-postgres-and-readiness.md#engine-and-connection-pool) · *2. Postgres and a readiness check*
- [Database URL anatomy](../sprint-0/02-postgres-and-readiness.md#database-url-anatomy) · *2. Postgres and a readiness check*
- [pydantic-settings](../sprint-0/02-postgres-and-readiness.md#pydantic-settings) · *2. Postgres and a readiness check*
- [FastAPI dependency injection](../sprint-0/02-postgres-and-readiness.md#fastapi-dependency-injection) · *2. Postgres and a readiness check*
- [Test isolation](../sprint-0/02-postgres-and-readiness.md#test-isolation) · *2. Postgres and a readiness check*
- [`monkeypatch`](../sprint-0/02-postgres-and-readiness.md#monkeypatch) · *2. Postgres and a readiness check*
- [`lru_cache` and tests](../sprint-0/02-postgres-and-readiness.md#lru_cache-and-tests) · *2. Postgres and a readiness check*
- [`==` vs `is`](../sprint-0/02-postgres-and-readiness.md#vs-is) · *2. Postgres and a readiness check*
- [Session (unit of work)](../sprint-0/03-sqlalchemy-and-alembic.md#session-unit-of-work) · *3. SQLAlchemy sessions and Alembic*
- [Generator dependencies](../sprint-0/03-sqlalchemy-and-alembic.md#generator-dependencies) · *3. SQLAlchemy sessions and Alembic*
- [pytest fixtures](../sprint-0/03-sqlalchemy-and-alembic.md#pytest-fixtures) · *3. SQLAlchemy sessions and Alembic*
- [`DeclarativeBase` and metadata](../sprint-0/03-sqlalchemy-and-alembic.md#declarativebase-and-metadata) · *3. SQLAlchemy sessions and Alembic*
- [Naming conventions](../sprint-0/03-sqlalchemy-and-alembic.md#naming-conventions) · *3. SQLAlchemy sessions and Alembic*
- [Migrations (Alembic)](../sprint-0/03-sqlalchemy-and-alembic.md#migrations-alembic) · *3. SQLAlchemy sessions and Alembic*
- [Migration rules of thumb](../sprint-0/03-sqlalchemy-and-alembic.md#migration-rules-of-thumb) · *3. SQLAlchemy sessions and Alembic*
- [Stairway test](../sprint-0/03-sqlalchemy-and-alembic.md#stairway-test) · *3. SQLAlchemy sessions and Alembic*
- [Image vs container](../sprint-0/04-dockerfile.md#image-vs-container) · *4. Dockerfile and the containerised stack*
- [Layer caching](../sprint-0/04-dockerfile.md#layer-caching) · *4. Dockerfile and the containerised stack*
- [Multi-stage builds](../sprint-0/04-dockerfile.md#multi-stage-builds) · *4. Dockerfile and the containerised stack*
- [BuildKit mounts](../sprint-0/04-dockerfile.md#buildkit-mounts) · *4. Dockerfile and the containerised stack*
- [Container hardening basics](../sprint-0/04-dockerfile.md#container-hardening-basics) · *4. Dockerfile and the containerised stack*
- [Compose networking](../sprint-0/04-dockerfile.md#compose-networking) · *4. Dockerfile and the containerised stack*
- [`depends_on` conditions](../sprint-0/04-dockerfile.md#depends_on-conditions) · *4. Dockerfile and the containerised stack*
- [YAML anchors](../sprint-0/04-dockerfile.md#yaml-anchors) · *4. Dockerfile and the containerised stack*
- [Linter vs formatter vs type checker](../sprint-0/05-lint-types-precommit.md#linter-vs-formatter-vs-type-checker) · *5. Lint, types, test config and pre-commit*
- [What mypy strict catches, and what it can't](../sprint-0/05-lint-types-precommit.md#what-mypy-strict-catches-and-what-it-cant) · *5. Lint, types, test config and pre-commit*
- [pre-commit](../sprint-0/05-lint-types-precommit.md#pre-commit) · *5. Lint, types, test config and pre-commit*
- [pytest config](../sprint-0/05-lint-types-precommit.md#pytest-config) · *5. Lint, types, test config and pre-commit*
- [Make essentials](../sprint-0/06-makefile.md#make-essentials) · *6. Makefile*
- [GitHub Actions anatomy](../sprint-0/07-ci.md#github-actions-anatomy) · *7. GitHub Actions CI*
- [Action versions are maintainer conventions](../sprint-0/07-ci.md#action-versions-are-maintainer-conventions) · *7. GitHub Actions CI*
- [Reading a failed run from the terminal](../sprint-0/07-ci.md#reading-a-failed-run-from-the-terminal) · *7. GitHub Actions CI*
- [What pre-commit can't catch](../sprint-0/07-ci.md#what-pre-commit-cant-catch) · *7. GitHub Actions CI*
- [CI caching](../sprint-0/07-ci.md#ci-caching) · *7. GitHub Actions CI*
- [Static site generator](../sprint-0/08-journal-site.md#static-site-generator) · *8. Journal site*
- [Docs as code](../sprint-0/08-journal-site.md#docs-as-code) · *8. Journal site*
- [Strict builds as a link checker](../sprint-0/08-journal-site.md#strict-builds-as-a-link-checker) · *8. Journal site*
- [Heading anchors differ between renderers](../sprint-0/08-journal-site.md#heading-anchors-differ-between-renderers) · *8. Journal site*
- [Live reload](../sprint-0/08-journal-site.md#live-reload) · *8. Journal site*
- [Pages deployment with OIDC](../sprint-0/08-journal-site.md#pages-deployment-with-oidc) · *8. Journal site*
- [Job-level permissions and conditions](../sprint-0/08-journal-site.md#job-level-permissions-and-conditions) · *8. Journal site*
- [Path filters](../sprint-0/08-journal-site.md#path-filters) · *8. Journal site*
- [Non-default dependency groups](../sprint-0/08-journal-site.md#non-default-dependency-groups) · *8. Journal site*
