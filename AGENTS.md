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

All commands run from `backend/` (that's where the `Makefile` lives — there is no
root-level `Makefile`). Every target is scoped to one package/service; there is no
bare "build everything" command.

```bash
cd backend
make setup                    # bring up *-db + MinIO + RabbitMQ, run migrations (no seed, no *-api)
make demo                     # setup + seed (admin, demo products) + workers
make up_dev service=<svc>     # bring up dev profile (identity-api/catalog-api/support-api); omit service= for all
make test pkg=<member>        # pytest for one package (libs/<name> or services/<name>)
make check pkg=<member>       # ruff + mypy + vulture for one package
make architecture-check       # CQRS / dependency-direction gate (check_architecture.py)
make build service=<svc>      # docker compose build
```

## Repository map

`backend/libs/` contains shared packages (`kernel-domain`, `kernel-platform`,
`observability`, `test-support`). `backend/services/` contains `identity-service`,
`catalog-service`, and `support-service`, each with its own `tests/{unit,integration}/`.
`backend/tests/e2e/` holds the cross-service black-box suite (through an E2E-only
Nginx Gateway — there is no production API Gateway). There is no root-level `tests/`
directory. `docs/adr/` holds the ADR base (start at `docs/adr/README.md`);
`docs/architecture/backend_architecture.md` holds the accompanying diagrams and prose.

## Boundaries

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
