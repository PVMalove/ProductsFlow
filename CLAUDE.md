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
- **Config** (`app/settings.py`) is `pydantic-settings` reading `.env`; see `.env.example` for the full variable list (`DATABASE_URL`, `SECRET_KEY`, `ACCESS_TOKEN_TTL_HOURS`, `ADMIN_PASSWORD`, Postgres compose vars).

Everything else architecture-specific lives in `.claude/rules/architecture/*.md` and lazy-loads by path (YAML `paths:` frontmatter) instead of always sitting in this file:

| Rule | Triggers on |
|---|---|
| [repository.md](.claude/rules/architecture/repository.md) | `app/repository.py` |
| [auth.md](.claude/rules/architecture/auth.md) | `app/security.py`, `app/router/auth.py` |
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
