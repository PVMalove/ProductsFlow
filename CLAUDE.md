# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

### backend/ (isolated per-package environments, ADR 0020)

Five packages, each a flat directory with its own `pyproject.toml` and `.venv`: libs `kernel-domain`, `kernel-platform` (`backend/libs/<name>`); services `identity-service`, `catalog-service`, `support-service` (`backend/services/<name>`).

- Install deps for one package: `uv sync` from inside `backend/libs/<name>` or `backend/services/<name>` — each package has its own `.venv`, there is no shared `uv sync` from `backend/`.
- Lint/typecheck one package: `make check pkg=<member>` (from the repo root; ruff check, `mypy --explicit-package-bases`, ruff format --check, `vulture whitelist.py`), scoped to `libs/<member>` or `services/<member>` and running inside that package's own environment.
- Format one package: `make format pkg=<member>` (ruff format + ruff check --fix). `make lint pkg=<member>` = format then check.
- Test one package: `make test pkg=<member>` (`uv run pytest` inside the package directory), scoped to the same package directory.
- Generate a local RS256 dev key pair for identity: `make keys` — writes `backend/secrets/identity_jwt_private_key.pem` (git-ignored); point `IDENTITY_JWT_PRIVATE_KEY_PATH` in `.env` at it.
- Build service images: `make build service=<compose-service>` (`identity-api`/`catalog-api`/`support-api`), or `docker compose build` directly.
- Dev stack: `make up_dev service=<compose-service>` — base `docker-compose.yml` + `docker-compose.dev.yml` override (host ports 9010–9012, `APP_ENV=dev`).
- Prod stack: `make up_prod service=<compose-service>` — base + `docker-compose.prod.yml` override (host ports 9013–9015, `APP_ENV=prod`, `restart: unless-stopped`).
- Each service container gets only its own `*_DATABASE_URL` via `environment:` (ADR 0010 — not a blanket `env_file`); see `backend/.env.example` for the full variable list (`APP_ENV`, `IDENTITY_DATABASE_URL`, `IDENTITY_JWT_PRIVATE_KEY_PATH`, `IDENTITY_ACCESS_TOKEN_TTL_HOURS`, `CATALOG_DATABASE_URL`, `SUPPORT_DATABASE_URL`).
- `docker-compose.migrations.yml` is an empty stub for one-off bootstrap services (`alembic upgrade` + bucket-ensure + seed) once services have real Alembic revisions.
- CI (`.github/workflows/ci.yml`): `backend-lint` runs `make check pkg=<member>` as a matrix job per package; `backend-test` runs `make test pkg=<member>` as a matrix job over the packages; `backend-build` runs `docker compose build`.

## Architecture

`backend/` (ADR 0010, ADR 0020) is where all work happens. It is a set of isolated microservices (`identity-service`, `catalog-service`, `support-service`) and shared libraries (`kernel-domain`, `kernel-platform`, `observability`, `test-support`). 
- Services communicate asynchronously via the transactional outbox pattern using `kernel-platform`'s `OutboxPublisher` and workers (e.g. `identity-worker`).
- Synchronous interactions exist only when strictly necessary (e.g., fetching JWKS tokens via `IdentityClient`).

Everything else architecture-specific lives in `.claude/rules/architecture/*.md` and lazy-loads by path:

| Rule | Triggers on |
|---|---|
| [repository.md](.claude/rules/architecture/repository.md) | `backend/**/repository.py` |
| [auth.md](.claude/rules/architecture/auth.md) | `backend/**/security.py`, `backend/**/auth.py` |
| [audit.md](.claude/rules/architecture/audit.md) | `backend/**/audit.py`, `backend/**/models.py` |
| [errors.md](.claude/rules/architecture/errors.md) | `backend/**/errors.py` |
| [startup.md](.claude/rules/architecture/startup.md) | `backend/**/main.py`, `backend/**/db.py` |
| [testing.md](.claude/rules/architecture/testing.md) | `backend/**/tests/**`, `backend/**/conftest.py` |

[.claude/rules/karpathy-guidelines.md](.claude/rules/karpathy-guidelines.md) is unscoped — general coding behavior, loads every session like this file.

Domain-doc consumer rules lazy-load from [.claude/rules/domain/domain.md](.claude/rules/domain/domain.md) (`backend/**`, `tests/**`).

## Agent skills

Full command/skill reference: `docs/agents/harness-guide.md`.

### Issue tracker

Issues live in GitHub Issues (`github.com/PVMalove/ProductsFlow`), via the `gh` CLI. See `docs/agents/issue-tracker.md`.

### Triage labels

Custom namespaced taxonomy — not the upstream canonical five-role set. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context layout — `CONTEXT.md` + `docs/adr/` at the repo root. See `docs/agents/domain.md`.

### Git workflow

Ticket implementation always goes on `feature/<ticket-id>` + PR. Open PR only after explicit developer confirmation. See `docs/agents/git-workflow.md`.

### Parallel work (worktrees)

Only when explicitly asked: use the native `EnterWorktree`/`ExitWorktree` tools, not manual `git worktree` + `tmux`. See `docs/agents/worktrees.md`.

### Communication language

The agent must always respond and generate output exclusively in Russian, regardless of the language of the prompt.

### Artifacts management

Rules for saving intermediate specs and scratchpads locally. See `docs/agents/artifacts.md`.
