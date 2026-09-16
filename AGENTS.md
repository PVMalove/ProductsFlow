# ProductsFlow_AI

Canonical instructions for agents in this repository. More specific project instructions
override this file. Harness provenance and file hashes are recorded in `.harness/harness.lock`.

## Project

ProductsFlow_AI — Python-система управления каталогом товаров, реализованная в виде изолированных
библиотек и микросервисов в директории `backend/`.

- Type: software
- Tools/stack: python
- Capabilities: pvmalove-suite
- Stage: active development
- Tracker: GitHub Issues in `PVMalove/ProductsFlow`, operated through `gh`
- Base branch: `master`

Document the tracker and its workflow in this repository when the project uses one.

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

Additionally, from AGENTS.md:
```bash
cd backend
make setup                    # bring up *-db + MinIO + RabbitMQ, run migrations (no seed, no *-api)
make demo                     # setup + seed (admin, demo products) + workers
make architecture-check       # CQRS / dependency-direction gate (check_architecture.py)
```

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

## Repository map

`backend/libs/` contains shared packages (`kernel-domain`, `kernel-platform`,
`observability`, `test-support`). `backend/services/` contains `identity-service`,
`catalog-service`, and `support-service`, each with its own `tests/{unit,integration}/`.
`backend/tests/e2e/` holds the cross-service black-box suite (through an E2E-only
Nginx Gateway — there is no production API Gateway). There is no root-level `tests/`
directory. `docs/adr/` holds the ADR base (start at `docs/adr/README.md`);
`docs/architecture/backend_architecture.md` holds the accompanying diagrams and prose.

## Boundaries

- Language: The agent must always respond and generate output exclusively in Russian, regardless of the language of the prompt.
- Artifacts: Rules for saving intermediate specs and scratchpads locally. See `docs/agents/artifacts.md`.
- Allowed: modify active code under `backend/`, its tests, and required documentation.
- Ask first: opening a PR, changing the issue/workflow scope, or destructive database actions.
- Do not touch: unrelated dirty work, secrets, `.env`, or generated caches/artifacts.

## Definition of Done

The requested behavior is implemented with tests, the relevant checks pass, architecture
and domain documentation are updated when needed, and changes are committed only on an
isolated feature branch.

## Delivery

Implementation follows the issue-first workflow. Use `/implement` for an `afk` ticket and
`/to-guide` for a `hitl` ticket. Open a PR only after explicit developer confirmation;
never merge automatically.

Preserve unrelated dirty changes and live worktrees. The active project skill or an explicit user
instruction chooses the checkout strategy.

## Runtime

- Skills live in `.harness/skills` and are discovered through `.agents/skills` and
  `.claude/skills`.
- Harness-managed skill files and their version lock live in `.harness/`.
- Capability updates are explicit and require a reviewed harness diff.
- В Orca-managed сессии (признак: `TERM_PROGRAM=Orca` или заданы `ORCA_WORKSPACE_ID`/`ORCA_WORKTREE_ID`
  в окружении) веди свою собственную работу по фазам ("Run a phased workflow") — это про то, как
  координатор структурирует шаги **в своей же сессии**, а не сигнал отправлять каждую задачу другому
  агенту. Подавляющее большинство задач координатор выполняет сам, без спавна кого-либо; заводить
  оркестратор — это отдельное, осознанное решение, а не поведение по умолчанию для любой задачи.
  Правило про supervised-цепочку применяется **только в момент, когда координатор всё же решает
  делегировать саб-агенту** — и только если у этого саб-агента есть отдельный deliverable (код,
  текст PR, отчёт и т.п.): тогда обязателен `Run → Task → worker-start` (предпочтительно) или
  `dispatch --inject` → `orca orchestration check --wait` до получения `worker_done`/`escalation`.
  Обычный `Spawned`/`default`-subagent (без provenance Orca, lifecycle preamble и контроля
  `worker_done`) допустим как узкое исключение — для тривиального in-session lookup'а без
  отдельного deliverable (пример: `Explore` для поиска кода). Делегирование результата (например,
  подготовка тела PR через `pr-composer`) не считается таким исключением и **обязано** идти
  supervised-цепочкой — но только когда делегирование саб-агенту вообще происходит.
  **Последствие нарушения (недостаточно):** координатор не получает `worker_done` и не продолжает
  workflow автоматически — пользователю приходится вручную «пинать» сессию на каждый следующий шаг.
  **Последствие нарушения (избыточно):** заворачивать в оркестратор задачи, которые координатор мог
  выполнить сам в текущей сессии, впустую тратит токены и время — это тоже нарушение правила, не
  его добросовестное исполнение.
  **`--agent` в `worker-start` — свой рантайм по умолчанию.** У `orca orchestration worker-start`
  флаг `--agent` обязателен и явный (`(--agent <agent> | --terminal <handle>)`) — Orca сама никогда
  не подставляет `claude`/`claude-code` по умолчанию, это всегда осознанный выбор того, кто собирает
  команду. Координатор передаёт `--agent`, совпадающий с его собственным рантаймом (Codex-координатор
  → `--agent codex`, Claude-координатор → `--agent claude`), если только пользователь явно не попросил
  воркера другого семейства. `.claude/agents/*.md` (например, `pr-composer.md`) — это спецификация
  задачи в markdown, а не Claude-Code-специфичный вызов: любой рантайм может открыть этот файл и
  выполнить описанные в нём шаги сам, без необходимости поднимать воркера другого семейства ради
  одного File-based агента.
  Оценивай доставленные результаты каждого этапа перед запуском следующего, продолжая workflow
  в той же сессии. Избегай параллельной работы или разделения на несколько worktrees без
  явного запроса. В обычном рантайме заверши ход после запуска и дождись уведомления harness.

## Known pitfalls

All project code belongs under `backend/`. Each backend package has
its own `pyproject.toml`, but they share a single `backend/uv.lock` and `.venv`. The project requires Python 3.14. Preserve
unrelated dirty changes and run the quality gate before PR creation.
