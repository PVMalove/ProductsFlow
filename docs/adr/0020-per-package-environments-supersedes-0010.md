# 0020. Изолированные окружения на пакет вместо общего uv-workspace (supersedes ADR 0010)

`backend/` сегодня — единый `uv`-workspace (ADR 0010): один `.venv`, один корневой `uv.lock`, один общий `[dependency-groups] dev` в `backend/pyproject.toml`. Три конкретные проблемы, вскрывшиеся на живом коде (issue #129):

1. **Общий `.venv` конфликтует с доменным именованием пакетов.** Каждый сервис-пакет называется `<domain>_service` (`identity_service`, `catalog_service`, `support_service`) именно потому, что общее окружение не переживёт коллизию коротких имён (`identity`, `catalog`, `support`) между сервисами — суффикс `_service`/`_domain`/`_platform` существует не как осознанный домен-нейминг, а как обходной путь вокруг модели окружений.
2. **Общий `[dependency-groups] dev` — вынужденный костыль, а не дизайн.** Per-package dev-группы в uv workspace не суммируются, а переопределяют друг друга: чтобы одновременно дать `identity-service` его тестовые зависимости (asyncpg, pika, testcontainers, sqlalchemy) и `kernel-platform` — его (реальный код `identity-service` как тестовая зависимость round-trip JWKS-теста, ADR 0011/issue #83), все они свалены в один список на корне `backend/pyproject.toml` с комментариями «только для X». Границы зависимостей между пакетами скрыты, каждый пакет транзитивно тянет чужие dev-зависимости.
3. **Лишний уровень вложенности (`backend/src/libs/`, `backend/src/services/`) без функциональной необходимости.** Внешний `src/` был осмыслен как разделение «Python-код» vs «инфраструктура/конфиги» на уровне `backend/`, но при переходе на независимые окружения на пакет он не даёт ничего сверх того, что уже даёт сама директория `backend/`.

Решение: единый uv-workspace заменяется пятью независимыми пакетами, каждый со своим `uv.lock`/окружением, лежащими прямо под `backend/services/*` и `backend/libs/*` — без промежуточного внешнего `src/`. Внутренний src-layout каждого пакета (`<pkg-dir>/src/<pkg>/`) не меняется.

```
backend/
  pyproject.toml            общий [tool.ruff]/[tool.mypy]-конфиг; без [tool.uv.workspace], без общих dependency-groups
  libs/
    kernel-domain/          свой pyproject.toml + uv.lock + src/kernel_domain/
    kernel-platform/        свой pyproject.toml + uv.lock + src/kernel_platform/
    observability/          свой pyproject.toml + uv.lock + src/observability/   — новый, выделен из kernel-platform.logging
  services/
    identity-service/       свой pyproject.toml + uv.lock + src/identity/       — переименован из identity_service
    catalog-service/        свой pyproject.toml + uv.lock + src/catalog/        — переименован из catalog_service
    support-service/        свой pyproject.toml + uv.lock + src/support/        — переименован из support_service
```

- **Изоляция окружений.** Каждый пакет резолвит зависимости независимо: свой `uv sync`/`uv run` внутри директории пакета, свой `uv.lock`. Межпакетные зависимости внутри монорепо (сервис → lib) объявляются как path-зависимость: editable в dev-окружении, `--no-editable` при сборке production-образа — та же двухстадийная схема Dockerfile, что и раньше, применяется к каждому пакету отдельно вместо `--package` из общего workspace.
- **Переименование пакетов.** Имя внутреннего Python-пакета отделяется от суффикса `_service`/`_domain`/`_platform`: `identity_service` → `identity`, `catalog_service` → `catalog`, `support_service` → `support`. Директории workspace-членов (`identity-service/`, `catalog-service/`, `support-service/`, kebab-case) не меняются. Дистрибутивные имена (`[project].name`, значения `pkg=`/`service=` в Makefile и compose) тоже не меняются — это переименование внутреннего пакета, не публичного интерфейса.
- **Выделение `observability`.** `kernel-platform`'s `logging/`-подпакет (форматтеры, ContextVar, TokenVerifier, RequestContextMiddleware — ADR 0016) самодостаточен (нет обратных зависимостей от остальной части `kernel-platform`) и потребляется сейчас только `identity-service`, поэтому выделяется в собственный пакет `observability`.
- **Round-trip JWKS-тест** (ADR 0011/issue #83) переезжает из тестов `kernel-platform` в тесты `identity-service`: сервис и так зависит от `kernel-platform`, поэтому тест логично живёт там и импортирует `kernel-platform`/`identity` в естественном направлении (сервис → lib), а не наоборот. `kernel-platform`'s собственный тест `IdentityClient.fetch_current_user` возвращается к fake-стабу — тот же приём, что уже используется для `fetch_current_user` в его нынешнем виде.
- **Makefile/CI.** Переключаются с `uv run --package <member>` (общий workspace) на выполнение команд внутри директории каждого пакета со своим `uv sync`/`uv run`. Матрица CI по member'ам сохраняется — джобы адресуют пакеты по директории вместо `--package`.

## Considered Options

- **Сохранение общего workspace, точечная правка dev-групп** — отклонено: проблема не в конкретных комментариях «только для X», а в том, что per-package dev-группы в uv workspace принципиально не суммируются. Любая точечная правка воспроизводит тот же костыль на следующем пакете с новой тестовой зависимостью на код другого пакета.
- **Приватный package-индекс вместо path-зависимостей** (публикация `kernel-domain`/`kernel-platform`/`observability` как обычных версионированных пакетов) — отклонено: вводит инфраструктуру (реестр пакетов, процесс релиза, семвер) ради проблемы, которую path-зависимости внутри монорепо решают без дополнительных частей. Сервисы и так всегда смотрят на HEAD kernel-пакетов (ADR 0013) — версионирование между ними намеренно не заводилось, и это решение не пересматривается.
- **Переименование `kernel-domain`/`kernel-platform`** (например, в `shared`) заодно с этой задачей — отклонено: имена этих пакетов не участвуют в статтере, который вызвал пересмотр (`kernel-domain`/`kernel-platform` не дублируют суффикс с содержимым директории), и объединение двух независимых переименований в одном PR усложняет ревью без выигрыша. Рассматривалось в ходе grilling-сессии по #129 вместе с гипотетической `infrastructure/`-директорией и отклонено по той же причине, что и она — нет опоры в реальном коде проекта.

## Consequences

- **ADR 0010 помечается superseded** этим решением в части общего workspace/`.venv`; текст и обоснование 0010 не переписываются — историческая ADR фиксирует, каким было решение на момент Фазы 0, а не то, каким оно стало.
- `backend/pyproject.toml` теряет `[tool.uv.workspace]` и общие `[dependency-groups]`, сохраняя только `[tool.ruff]`/`[tool.mypy]`-конфиг, общий для всех пакетов.
- `make check pkg=<member>`/`make test pkg=<member>` в `CLAUDE.md` меняют механику выполнения (per-package `uv sync`/`uv run` вместо `uv run --package`), но не публичный интерфейс команд — `pkg=`/`service=` продолжают адресовать те же имена.
- Ломающее изменение в `kernel-domain`/`kernel-platform`/`observability` больше не ловится единым `uv.lock` за один `uv sync` — обнаруживается CI-матрицей (свой job на pull зависимого пакета), на джобу позже, чем при общем workspace.
- Декомпозиция issue #129 (issues #131–134) реализует переезд по частям: `libs/` (#131), `identity-service` (#132), `catalog-service`/`support-service` (#133), снос shared-workspace оснастки в Makefile/CI/compose/CLAUDE.md (#134). Эта ADR фиксирует решение целиком, реализация растянута на них.
