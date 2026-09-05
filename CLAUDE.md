# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

### backend/ (per-package dependency declarations, shared workspace lock — see `docs/architecture/backend_architecture.md` §2)

Five packages, each a flat directory with its own `pyproject.toml` declaring its own dependencies: libs `kernel-domain`, `kernel-platform` (`backend/libs/<name>`); services `identity-service`, `catalog-service`, `support-service` (`backend/services/<name>`). `backend/pyproject.toml` declares `[tool.uv.workspace] members = ["libs/*", "services/*"]` and resolves into one shared `backend/uv.lock`/`backend/.venv` — reintroduced (Integration/e2e work) specifically so `backend/tests/e2e/` (which isn't inside any single package) has a coherent environment to run against. There is no per-package `uv.lock` anymore.

- Install/sync deps for one package: `uv sync --all-packages` from inside `backend/libs/<name>` or `backend/services/<name>` (that's what `make check`/`test`/`format` do) — this resolves the whole shared workspace lock, `cd` just scopes which package's lint/tests actually run.
- Lint/typecheck one package: `make check pkg=<member>` (from the repo root; ruff check, `mypy --explicit-package-bases`, ruff format --check, `vulture whitelist.py`), scoped to `libs/<member>` or `services/<member>` and running inside that package's own environment.
- Format one package: `make format pkg=<member>` (ruff format + ruff check --fix). `make lint pkg=<member>` = format then check.
- Test one package: `make test pkg=<member>` (`uv run pytest` inside the package directory), scoped to the same package directory.
- Generate a local RS256 dev key pair for identity: `make keys` — writes `backend/secrets/identity_jwt_private_key.pem` (git-ignored); point `IDENTITY_JWT_PRIVATE_KEY_PATH` in `.env` at it.
- Build service images: `make build service=<compose-service>` (`identity-api`/`catalog-api`/`support-api`), or `docker compose build` directly.
- Dev stack: `make up_dev service=<compose-service>` — base `docker-compose.yml` + `docker-compose.dev.yml` override (`gateway` is the sole published port, `8080:80`, `APP_ENV=dev`).
- Prod stack: `make up_prod service=<compose-service>` — base + `docker-compose.prod.yml` override (`gateway` is the sole published port, `80:80`, `APP_ENV=prod`, `restart: unless-stopped`).
- Each service container gets only its own `*_DATABASE_URL` via `environment:` (not a blanket `env_file`); see `backend/.env.example` for the full variable list (`APP_ENV`, `IDENTITY_DATABASE_URL`, `IDENTITY_JWT_PRIVATE_KEY_PATH`, `IDENTITY_ACCESS_TOKEN_TTL_HOURS`, `CATALOG_DATABASE_URL`, `CATALOG_IDENTITY_BASE_URL`, `SUPPORT_DATABASE_URL`).
- Migrations/seeding run through one-off `*-bootstrap` Compose services (`api/bootstrap.py` per service), never in FastAPI's `lifespan`; `make setup` runs migrations for all three, `make demo` adds seeding.
- CI (`.github/workflows/ci.yml`): `backend-lint` runs `make check pkg=<member>` as a matrix job per package; `backend-test` runs `make test pkg=<member>` as a matrix job over the packages; `backend-build` runs `docker compose build`.

## Architecture

`backend/` is where all work happens — a set of isolated microservices (`identity-service`, `catalog-service`, `support-service`) and shared libraries (`kernel-domain`, `kernel-platform`, `observability`, `test-support`). A single Nginx gateway (`backend/infra/gateway/nginx.conf`) is the sole publicly exposed entry point in both dev (`8080:80`) and prod (`80:80`); `identity-api`/`catalog-api`/`support-api` no longer publish host ports in either profile. Full decision record: `docs/adr/` (start at `docs/adr/README.md`); diagrams and prose: `docs/architecture/backend_architecture.md`.

- Services communicate asynchronously via the transactional outbox pattern (`kernel-platform`'s `drain_events_to_outbox()` + `identity-worker`/`catalog-worker`/`support-worker`). `identity-service` is the only event producer.
- Synchronous interactions are the exception, not symmetric across services: `catalog-service` verifies JWTs via `IdentityClient`'s JWKS cache and makes a synchronous call to identity on a read-model cache miss or admin action; `support-service` verifies JWTs with a statically configured public key and never calls identity synchronously (deny-by-default instead). See `docs/adr/0005-security-auth-actor-contract.md`.

Everything else architecture-specific lives in `.claude/architecture/*.md` and lazy-loads by path:

| Rule | Triggers on |
|---|---|
| [repository.md](.claude/architecture/repository.md) | `backend/services/*/src/domain/repositories.py`, `backend/services/*/src/infrastructure/db/*_repository.py` |
| [auth.md](.claude/architecture/auth.md) | `backend/services/*/src/infrastructure/security/auth.py`, `backend/services/identity-service/src/core/security/*.py` |
| [audit.md](.claude/architecture/audit.md) | `backend/services/{identity,catalog}-service/src/infrastructure/db/audit.py` |
| [errors.md](.claude/architecture/errors.md) | `backend/libs/kernel-platform/src/kernel_platform/http/*.py` |
| [startup.md](.claude/architecture/startup.md) | `backend/services/*/src/api/main.py`, `backend/services/*/src/api/bootstrap.py` |
| [testing.md](.claude/architecture/testing.md) | `backend/services/*/tests/**`, `backend/tests/e2e/**` |

[.claude/rules/karpathy-guidelines.md](.claude/rules/karpathy-guidelines.md) is unscoped — general coding behavior, loads every session like this file.

Domain-doc consumer rules lazy-load from [.claude/domain/domain.md](.claude/domain/domain.md) (`backend/**`, `tests/**`).

## Agent skills

Full command/skill reference: `docs/agents/harness-guide.md`.

### Issue tracker

Issues live in GitHub Issues (`github.com/PVMalove/ProductsFlow`), via the `gh` CLI. See `docs/agents/issue-tracker.md`.

### Triage labels

Custom namespaced taxonomy — not the upstream canonical five-role set. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context layout — `CONTEXT.md` + `docs/adr/` at the repo root. See `.claude/domain/domain.md`.

### Git workflow

Ticket implementation always goes on `feature/<ticket-id>` + PR. Open PR only after explicit developer confirmation. See `docs/agents/git-workflow.md`.

### Parallel work (worktrees)

Only when explicitly asked: use the native `EnterWorktree`/`ExitWorktree` tools, not manual `git worktree` + `tmux`. See `docs/agents/worktrees.md`.

### Communication language

The agent must always respond and generate output exclusively in Russian, regardless of the language of the prompt.

### Artifacts management

Rules for saving intermediate specs and scratchpads locally. See `docs/agents/artifacts.md`.
