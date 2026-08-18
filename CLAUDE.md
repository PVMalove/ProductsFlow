# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

Package/dependency management is via `uv` (see `uv.lock`). Requires Python 3.14 (`.python-version`).

- Install deps: `uv sync`
- Run the API locally: `uv run uvicorn app.main:app --reload` (needs a reachable Postgres — see `make up_dev` below; DB URL comes from `.env` / `DATABASE_URL`)
- Test: `make test` (= `uv run pytest`)
  - Single test: `uv run pytest tests/unit/test_schemas.py::test_name`
  - Integration tests (`tests/integration/`) spin up a real Postgres via `testcontainers` (session-scoped, see root `conftest.py`) — Docker must be running. Unit tests (`tests/unit/`) don't need Docker.
- Coverage: `make coverage` (`service=app` by default)
- Format: `make format` (ruff format + ruff check --fix)
- Lint/typecheck: `make check` (ruff check, `mypy --explicit-package-bases`, ruff format --check, `vulture ./whitelist.py`). `whitelist.py` at the repo root suppresses vulture false positives (currently just the unused `cls` in `app/schemas.py`'s `@field_validator` classmethods) — regenerate entries with `uv run vulture --make-whitelist .` if new false positives show up. `whitelist.py` is excluded from ruff/mypy (`[tool.ruff] extend-exclude`, `[tool.mypy] exclude`) since it's not meant to be valid/typed Python.
- `make lint` = format then check.
- Scope check/format/lint to a path: `make check path=app`.

### Database migrations (Alembic)

- Local (uses the `DATABASE_URL` in `.env` directly): `make db-revision msg="..."`, `make db-upgrade`, `make db-downgrade`, `make db-current`, `make db-history`.
- Dockerized (via a one-off `*_migrations` compose service): `make make_migration message="..."`, `make migrate`, `make downgrade`.
- The app also runs migrations itself on every startup (see Architecture below) — for local dev you generally don't need to run `db-upgrade` manually before `uvicorn`.

### Docker Compose

- `make up_dev` — Postgres only (profile `dev`, port `7600`), for running the API locally against it.
- `make up_prod` — Postgres + the API, both dockerized (profile `prod`, API on port `9000`).
- `make down_dev` / `make down_prod`, `make shell service=app`, `make logs service=app`, `make build`.

## Architecture

Single-service FastAPI app (`app/`), layered `router → repository → SQLAlchemy model`, with Pydantic schemas (`app/schemas.py`) as the response/validation boundary.

- **Routers** (`app/router/auth.py`, `products.py`, `users.py`) depend on repositories and on the `CurrentUser` / `AdminUser` typed dependencies from `app/security.py` for auth gating; they raise `HTTPException` directly for domain errors (not-found, forbidden).
- **Repositories** (`app/repository.py`) are the only place that touches SQLAlchemy sessions/queries. Note the mixed return convention: `ProductRepository` and the audit-log repositories return Pydantic `*Response` schemas (already validated from ORM rows), while `UserRepository` returns raw `User` ORM instances — because `app/security.py` needs `password_hash` off the returned object. Match whichever convention the repository you're editing already uses.
- **Auth**: JWT bearer tokens (PyJWT, `HS256`), issued from `/auth/login` (`app/router/auth.py`) and read via `OAuth2PasswordBearer` in `app/security.py`. `get_current_user` rejects a deactivated account (`User.is_active is False`) with 403 *before* any role/ownership check runs — deactivation is an authentication-layer concept, not authorization (see `CONTEXT.md`). `require_admin`/`AdminUser` layers role checks on top of `CurrentUser`.
- **Audit logging** (`app/audit.py`) is implemented as SQLAlchemy ORM event listeners (`after_insert`/`before_update`/`before_delete` on `User` and `Product`), not as explicit calls in routers/repositories — any ORM-level mutation of these models produces an audit row automatically; raw SQL or bulk operations would bypass it. Listeners have no access to the request, so the acting user id is threaded through a `ContextVar` (`current_actor_id`), set per-request by `actor_context_middleware` in `app/main.py`, which decodes the bearer token independently of the `get_current_user` dependency.
- `ProductAuditLog.product_id` deliberately has no `ForeignKey` to `products` — deleting a product is a hard delete, and the audit trail must survive the row it references (see `CONTEXT.md` and the comment in `app/models.py`).
- **Startup lifecycle** (`lifespan` in `app/main.py`): runs Alembic migrations programmatically (`app/db.py:run_migrations`, via a sync `_run_upgrade` callback executed inside the async engine connection) and then seeds an admin user + demo products (`app/db.py:seed_db`) before the app starts serving. `conftest.py` reuses `_run_upgrade` directly against its testcontainers Postgres rather than duplicating migration setup.
- **Error handling** is centralized in `app/errors.py`: exception handlers translate Pydantic `RequestValidationError` and SQLAlchemy `IntegrityError` into Russian-language JSON error bodies, driven by the `FIELD_NAMES` / `ERROR_TEMPLATES` lookup tables. Extend those tables for new fields/error types rather than raising ad hoc `HTTPException`s for validation failures.
- **Config** (`app/settings.py`) is `pydantic-settings` reading `.env`; see `.env.example` for the full variable list (`DATABASE_URL`, `SECRET_KEY`, `ACCESS_TOKEN_TTL_HOURS`, `ADMIN_PASSWORD`, Postgres compose vars).
- **Tests**: root `conftest.py` provides a session-scoped real Postgres (testcontainers), one connection+SAVEPOINT transaction per test for isolation, and an `httpx.AsyncClient` wired to the app via `ASGITransport` with `get_session` overridden to the test session. Integration tests exercise real HTTP + DB round trips; unit tests cover pure logic (schema validators, security helpers, error-message formatting) without a DB.

## Agent skills

### Issue tracker

Issues live in GitHub Issues (`github.com/PVMalove/ProductsFlow`), via the `gh` CLI. See `docs/agents/issue-tracker.md`.

### Triage labels

Custom namespaced taxonomy (`hitl`/`afk` execution mode + `type::*` + `workflow::*` + context labels) — not the upstream canonical five-role set. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context layout — `CONTEXT.md` + `docs/adr/` at the repo root. See `docs/agents/domain.md`.

### Git workflow

Ticket implementation always goes on `feature/<ticket-id>` + PR, never straight to `master`. See `docs/agents/git-workflow.md`.

### Communication language

The agent must always respond and generate output exclusively in Russian, regardless of the language of the prompt.

### Artifacts management

Rules for saving intermediate specs and scratchpads locally. See `docs/agents/artifacts.md`.
