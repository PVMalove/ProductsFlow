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

Use `N/A` for command slots that do not apply to this project.

```bash
make install       # setup
make up_dev        # run local development dependencies
make test          # test
make check         # lint/typecheck/format checks
make build         # build Docker images
```

## Repository map

`backend/libs/` contains shared packages (`kernel-domain`, `kernel-platform`,
`observability`, `test-support`). `backend/services/` contains `identity-service`,
`catalog-service`, and `support-service`.
`tests/` contains the root regression suite; `docs/` contains architecture, workflow,
and ADR documentation.

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
  в окружении) **всегда** используй стратегию **"Run a phased workflow"** по умолчанию —
  это MUST, не рекомендация.
  Supervised-цепочка **обязательна** для любого сабагента, который порождает отдельный процесс и
  что-то доставляет (код, текст PR, отчёт и т.п.): `Run → Task → worker-start` (предпочтительно)
  или `dispatch --inject` → `orca orchestration check --wait` до получения `worker_done`/`escalation`.
  Обычный `Spawned`/`default`-subagent (без provenance Orca, lifecycle preamble и контроля
  `worker_done`) допустим **только** как узкое исключение — для тривиального in-session lookup'а без
  отдельного deliverable (пример: `Explore` для поиска кода). Делегирование результата (например,
  подготовка тела PR через `pr-composer`) не считается таким исключением и **обязано** идти
  supervised-цепочкой.
  **Последствие нарушения:** координатор не получает `worker_done` и не продолжает workflow
  автоматически — пользователю приходится вручную «пинать» сессию на каждый следующий шаг
  (открытие PR, публикация отчёта и т.п.), что и является наблюдаемым симптомом этого антипаттерна.
  Оценивай доставленные результаты каждого этапа перед запуском следующего, продолжая workflow
  в той же сессии. Избегай параллельной работы или разделения на несколько worktrees без
  явного запроса. В обычном рантайме заверши ход после запуска и дождись уведомления harness.

## Known pitfalls

All project code belongs under `backend/`. Each backend package has
its own environment and `pyproject.toml`. The project requires Python 3.14. Preserve
unrelated dirty changes and run the quality gate before PR creation.
