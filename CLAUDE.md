# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

`backend/` is where new work happens — isolated per-package environments (ADR 0020), not a shared `uv` workspace. The repo root (`app/`, root `Makefile`/`pyproject.toml`/`Dockerfile`/`docker-compose.yml`) is the frozen monolith (see Architecture below) — its local check/test targets still work and remain useful for regression sanity while `backend/`'s services are extracted.

### backend/ (isolated per-package environments, ADR 0020)

Five packages, each a flat directory with its own `pyproject.toml` and `.venv`: libs `kernel-domain`, `kernel-platform` (`backend/libs/<name>`); services `identity-service`, `catalog-service`, `support-service` (`backend/services/<name>`). all three services now follow ADR 0026; `identity-service` and `catalog-service` contain the extracted runtime code — RS256 token signing/verification and a public `/.well-known/jwks.json` (ADR 0011, issue #82), plus its first Postgres table and second process: an Alembic revision creating `outbox_messages`, designed for the bootstrap pattern rather than `lifespan` (ADR 0014/0017 — the actual bootstrap compose service isn't wired up yet, this revision applies manually via the new `make db-upgrade pkg=<service>`), and an `identity-worker` entrypoint (`python -m presentation.worker` — same image as `identity-api`, different `CMD` per ADR 0010) draining it via `kernel-platform`'s `OutboxPublisher` on a fixed-interval poll (issue #100, happy path — no `SELECT ... FOR UPDATE SKIP LOCKED`/backoff/`LISTEN`-`NOTIFY` yet, those are issues #101–102) — `kernel-platform` has its first real code — a single `IdentityClient` with `verify_token()` (JWKS-caching RS256 verification against `identity-service`'s real signing/JWKS code via an in-process ASGI round-trip test, ADR 0011, issue #83) and `fetch_current_user()` (`GET /api/v1/users/me` sync fallback per ADR 0012, tested against a fake stub since `identity-service` has no `User` domain yet, issue #87), plus the `OutboxMessage` model and `OutboxPublisher` (ADR 0014, issue #100) — and `kernel-domain` has its first real code: stdlib-only `Result`/`Result[T]` and `Error`/`ErrorType` (ADR 0013, issue #90) — issues #73–75 built the original workspace/Docker/compose/CI scaffolding ahead of that, since superseded by ADR 0020's per-package layout (issues #131–134). Requires Python 3.14 (each package's own `pyproject.toml` `requires-python`).

- Install deps for one package: `uv sync` from inside `backend/libs/<name>` or `backend/services/<name>` — each package has its own `.venv`, there is no shared `uv sync` from `backend/`.
- Lint/typecheck one package: `make check pkg=<member>` (from `backend/`; ruff check, `mypy --explicit-package-bases`, ruff format --check, `vulture whitelist.py`), scoped to `libs/<member>` or `services/<member>` and running inside that package's own environment.
- Format one package: `make format pkg=<member>` (ruff format + ruff check --fix). `make lint pkg=<member>` = format then check.
- Test one package: `make test pkg=<member>` (`uv run pytest` inside the package directory), scoped to the same package directory.
- Generate a local RS256 dev key pair for identity: `make keys` — writes `backend/secrets/identity_jwt_private_key.pem` (git-ignored); point `IDENTITY_JWT_PRIVATE_KEY_PATH` in `.env` at it.
- Build service images: `make build service=<compose-service>` (`identity-api`/`catalog-api`/`support-api`), or `docker compose build` directly.
- Dev stack: `make up_dev service=<compose-service>` — base `docker-compose.yml` + `docker-compose.dev.yml` override (host ports 9010–9012, `APP_ENV=dev`).
- Prod stack: `make up_prod service=<compose-service>` — base + `docker-compose.prod.yml` override (host ports 9013–9015, `APP_ENV=prod`, `restart: unless-stopped`).
- Each service container gets only its own `*_DATABASE_URL` via `environment:` (ADR 0010 — not a blanket `env_file`); see `backend/.env.example` for the full variable list (`APP_ENV`, `IDENTITY_DATABASE_URL`, `IDENTITY_JWT_PRIVATE_KEY_PATH`, `IDENTITY_ACCESS_TOKEN_TTL_HOURS`, `CATALOG_DATABASE_URL`, `SUPPORT_DATABASE_URL`).
- `docker-compose.migrations.yml` is currently an empty stub — will hold one-off bootstrap services (`alembic upgrade` + bucket-ensure + seed) once services have real Alembic revisions.
- CI (`.github/workflows/ci.yml`): `backend-lint` runs `make check pkg=<member>` as a matrix job per package; `backend-test` runs `make test pkg=<member>` as a matrix job over the packages with tests so far (`identity-service`, `kernel-platform`, `kernel-domain`); `backend-build` runs `docker compose build`.

### app/ (frozen monolith)

- Install deps (from repo root): `uv sync`.
- Run locally: `uv run uvicorn app.main:app --reload` (needs a reachable Postgres — see `make up_dev` below; DB URL comes from `.env` / `DATABASE_URL`).
- Test: `make test` (= `uv run pytest`)
  - Single test: `uv run pytest tests/unit/test_schemas.py::test_name`
  - Integration tests (`tests/integration/`) spin up a real Postgres via `testcontainers` (session-scoped, see root `conftest.py`) — Docker must be running. Unit tests (`tests/unit/`) don't need Docker.
- Coverage: `make coverage` (`service=app` by default)
- Format: `make format` (ruff format + ruff check --fix)
- Lint/typecheck: `make check` (ruff check, `mypy --explicit-package-bases`, ruff format --check, `vulture ./whitelist.py`). `whitelist.py` at the repo root suppresses vulture false positives (currently just the unused `cls` in `app/schemas.py`'s `@field_validator` classmethods) — regenerate entries with `uv run vulture --make-whitelist .` if new false positives show up. `whitelist.py` is excluded from ruff/mypy (`[tool.ruff] extend-exclude`, `[tool.mypy] exclude`) since it's not meant to be valid/typed Python.
- `make lint` = format then check.
- Scope check/format/lint to a path: `make check path=app`.
- Local Alembic migrations (uses the `DATABASE_URL` in `.env` directly): `make db-revision msg="..."`, `make db-upgrade`, `make db-downgrade`, `make db-current`, `make db-history`. The app also runs migrations itself on every startup (see Architecture below) — for local dev you generally don't need to run `db-upgrade` manually before `uvicorn`.
- Docker Compose: `make up_dev` (Postgres + MinIO, profile `dev`, DB port `7600`) / `make up_prod` (Postgres + MinIO + the API, profile `prod`, API on port `9000`) / `make down_dev` / `make down_prod` / `make shell service=app` / `make logs service=app` / `make build`.

## Architecture

`app/` is now the **frozen monolith** (ADR 0010): a read-only reference kept for behavior comparison while `identity`/`catalog`/`support` are extracted into `backend/`, not modified further, and not built or tested by CI — its local `make check`/`make test` still work for regression sanity in the meantime. Layered `router → repository → SQLAlchemy model`, with Pydantic schemas (`app/schemas.py`) as the response/validation boundary.

- **Routers** (`app/routers/*.py` — `auth.py`, `categories.py`, `product_images.py`, `product_visibility.py`, `products.py`, `users.py`) depend on repositories and on the `CurrentUser` / `AdminUser` typed dependencies from `app/security.py` for auth gating; they raise `HTTPException` directly for domain errors (not-found, forbidden). `app/support/` is a separate self-contained package (own `models.py`/`repository.py`/`router_admin.py`/`router_user.py`/`schemas.py`) for support tickets, not wired through `app/routers/`.
- **Config** (`app/settings.py`) is `pydantic-settings` reading `.env`; see `.env.example` for the full variable list (`DATABASE_URL`, `SECRET_KEY`, `ACCESS_TOKEN_TTL_HOURS`, `ADMIN_PASSWORD`, Postgres compose vars).

`backend/` (ADR 0010) is where new work happens — five isolated per-package environments (ADR 0020; see Commands above), each with its own `pyproject.toml`, `.venv`, `Dockerfile`, and `docker-compose.yml` presence, currently still empty skeletons for `catalog-service`/`support-service`: the Docker/compose and CI matrix (issues #73–75), later flattened onto per-package isolation (issues #131–134), landed ahead of any domain code, which is the subject of later phases of TD-01 (issue #59).

Everything else architecture-specific lives in `.claude/rules/architecture/*.md` and lazy-loads by path (YAML `paths:` frontmatter) instead of always sitting in this file:

| Rule | Triggers on |
|---|---|
| [repository.md](.claude/rules/architecture/repository.md) | `app/repository.py` |
| [auth.md](.claude/rules/architecture/auth.md) | `app/security.py`, `app/routers/auth.py` |
| [audit.md](.claude/rules/architecture/audit.md) | `app/audit.py`, `app/models.py`, `app/main.py` |
| [errors.md](.claude/rules/architecture/errors.md) | `app/errors.py` |
| [startup.md](.claude/rules/architecture/startup.md) | `app/main.py`, `app/db.py` |
| [testing.md](.claude/rules/architecture/testing.md) | `tests/**`, `conftest.py` |

[.claude/rules/karpathy-guidelines.md](.claude/rules/karpathy-guidelines.md) is unscoped (no `paths:`) — general coding behavior, loads every session like this file.

Domain-doc consumer rules (read `CONTEXT.md`/`docs/adr/` before touching source) similarly lazy-load from [.claude/rules/domain/domain.md](.claude/rules/domain/domain.md) (`app/**`, `tests/**`) — same content as `docs/agents/domain.md`, kept in sync manually.

## Agent skills

Full command/skill reference (all 25 `.harness/` skills + project-specific `qa-gate`/`pr-composer`, the 6 locally-customized skills, hooks): `docs/agents/harness-guide.md`.

### Issue tracker

Issues live in GitHub Issues (`github.com/PVMalove/ProductsFlow`), via the `gh` CLI. See `docs/agents/issue-tracker.md`.

### Triage labels

Custom namespaced taxonomy (`hitl`/`afk` execution mode + `type::*` + `workflow::*` + context labels) — not the upstream canonical five-role set. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context layout — `CONTEXT.md` + `docs/adr/` at the repo root. See `docs/agents/domain.md`.

### Git workflow

Ticket implementation always goes on `feature/<ticket-id>` + PR, never straight to `master`; after the PR is open, the agent pauses for the developer's review-or-changes decision and never merges it itself. See `docs/agents/git-workflow.md`.

### Parallel work (worktrees)

Only when explicitly asked: use the native `EnterWorktree`/`ExitWorktree` tools (or `isolation: "worktree"` on a subagent), not manual `git worktree` + `tmux`. See `docs/agents/worktrees.md`.

### Communication language

The agent must always respond and generate output exclusively in Russian, regardless of the language of the prompt.

### Artifacts management

Rules for saving intermediate specs and scratchpads locally. See `docs/agents/artifacts.md`.
