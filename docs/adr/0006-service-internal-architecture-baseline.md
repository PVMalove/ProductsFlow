# 0006. Канон внутренней архитектуры сервиса: Hexagonal, Always-Valid Domain, CQRS, Unit of Work

**Статус:** Accepted

Три сервиса (`identity-service`, `catalog-service`, `support-service`) строятся по одному канону — Hexagonal Architecture (Ports & Adapters) с локальным CQRS и явным Unit of Work.

## Слои и направление зависимостей

```
<service>/src/
  domain/            сущности, value objects, repository-порты, доменные события
    entities/
    value_objects/
    events/
    repositories.py
    unit_of_work.py
  application/        use case
    commands/
    queries/
    ports/            (опционально — внешние read-порты вроде IdentityGateway)
  infrastructure/     адаптеры: SQLAlchemy, S3, IdentityClient, RabbitMQ-консьюмер
    db/
    security/
  api/                FastAPI-роутеры, HTTP-схемы, composition root
  core/                кросс-срезная политика сервиса (settings и т. п.)
  common/              локальные простые утилиты
tests/
  unit/  integration/  e2e/  performance/
k8s/  docs/  ci/  scripts/
```

Правило направления: `api → application → domain`; `infrastructure` реализует порты `domain`/`application` и подключается в composition root. `domain`/`application` не импортируют `infrastructure`, FastAPI, SQLAlchemy — импорт `kernel_platform` из `domain` допускается только для чистых stdlib-контрактов (`Result`, `pagination`), не для HTTP/ORM-типов. Это проверяется автоматически: `python backend/scripts/check_architecture.py --strict` (тот же gate — `make -C backend architecture-check`, тот же в CI) печатает blocking `ERROR` на любое нарушение направления или смешение command/query-модулей.

**Тонкие роутеры.** Обработчик FastAPI-эндпоинта — маппинг HTTP-запроса в command/query, один вызов handler'а и трансляция `Result` в ответ через общий exception-handling ([ADR 0003](0003-centralized-error-handling.md)); типичный обработчик — три строки (построить command/query из зависимости, вызвать handler, вернуть `match_result`/`match_created`). Бизнес-логика, оркестрация нескольких шагов и прямые обращения к репозиториям/сессии в роутере не допускаются.

## Домен: kernel-domain и Always-Valid Model

`kernel-domain` — общая для всех сервисов библиотека без единой внешней зависимости (только stdlib); домен сервиса имеет право импортировать только её.

- **`Result`/`Result[T]`** (`is_ok`/`is_err`) и **`Error`** (`code`, `description`, `type: ErrorType`) заменяют исключения для бизнес-правил ([ADR 0003](0003-centralized-error-handling.md)). Ожидаемый отказ — нормальный результат use case, не exception.
- **Сущности не создаются напрямую.** Прямой вызов `__init__` инкапсулирован приватным маркером.
  - **`create(...) -> Result[Entity]`** — публичная точка входа для *нового* агрегата: валидирует бизнес-инварианты (формат email, диапазон цены и т. п.) и может провалиться.
  - **`reconstitute(...) -> Entity`** — восстановление *уже существующего* агрегата из хранилища: строки, прошедшей персистентность, доверяют — повторная валидация бизнес-правил не выполняется, метод не возвращает `Result` и не может провалиться по бизнес-причине. Единственный вызывающий `reconstitute` — repository-адаптер при маппинге ORM-строки в доменную сущность; вызов `reconstitute` из application-слоя — признак утечки инфраструктурной заботы наружу.
- **`Entity.pull_events()`** — атомарное «забрать и очистить» накопленные `DomainEvent`, не два отдельных шага.
- **`DomainEvent`** — общий контракт для транзакционного outbox (детали и происхождение — [ADR 0010](0010-identity-service-event-integration.md)): два dataclass-поля с дефолтом (`event_type: str = ""`, `aggregate_type: str = ""`) и два метода-примитива (`aggregate_id() -> uuid.UUID`, `to_payload() -> dict[str, Any]`), каждый `raise NotImplementedError` в базовом классе.
- **`VisibilityPolicy`** — `typing.Protocol` с предикатом видимости; форма общая, реализация — нет: каждый сервис пишет свою против своей read-модели.

**Идентификаторы агрегатов — всегда GUID** (`uuid.UUID`, Postgres `UUID`), без исключений. Причина: агрегаты создаются в разных сервисах независимо, без единого источника последовательности, а угадываемый инкремент как PK — эксплуатационная дыра на границе микросервиса.

## Repository-контракт: порт в domain, реализация в infrastructure

Контракт персистентности агрегата — часть его bounded context, живёт в `<service>/domain/repositories.py`, не импортирует `application`/`infrastructure`/SQLAlchemy/FastAPI и не переезжает в `kernel-domain`. Один файл на сервис, пока у сервиса один агрегат с персистентностью.

- `application/` импортирует доменный `Protocol` только для тайп-хинтов зависимостей handler'ов; конкретная реализация подставляется на границе через `Depends()`-фабрику (API) или конструктор (composition root).
- Для одного агрегата concrete-реализация в `infrastructure/` использует нейтральное имя (`ProductRepository`), не имя, кодирующее технологию хранения.
- Read-side проекции (`owner_read_model`, `user_projection`) — CQRS query-стороны, читаемые query-хендлерами напрямую, не порт персистентности агрегата.

## CQRS: локальная опция, не платформенный фреймворк

Command/query-разделение — локальное соглашение application-слоя каждого сервиса, не общий `ICommand`/`IQuery`, dispatcher, registry или pipeline behavior.

- **Command** — неизменяемый входной DTO операции, которая может изменить состояние, породить доменное событие или отправить сообщение через outbox.
- **Query** — неизменяемый входной DTO чтения; не меняет состояние, не публикует события, без побочных эффектов.
- **Handler** — application-объект с одной ответственностью, получает порты конструктором, не знает о FastAPI/SQLAlchemy/RabbitMQ/S3.
- **Граница:** `application/commands/` и `application/queries/` не импортируют друг друга; общая логика выносится в domain или нейтральный application-helper.

```text
application/commands/
├── __init__.py
├── register_user.py
├── login.py
└── deactivate_user.py
application/queries/
├── __init__.py
└── get_user.py
```

## Unit of Work: транзакционная граница command handler'а

`kernel-platform` определяет generic `UnitOfWork` как **structural `Protocol`** (тот же стиль, что и у repository-портов — не `ABC`):

```python
class UnitOfWork(Protocol):
    async def __aenter__(self) -> Self: ...
    async def __aexit__(self, exc_type, exc, tb) -> None: ...
    async def commit(self) -> None: ...
    async def rollback(self) -> None: ...
```

Каждый сервис расширяет его собственным Protocol с атрибутами-репозиториями (`class CatalogUnitOfWork(UnitOfWork, Protocol): products: ProductRepository`). Конкретная реализация переиспользует уже существующую request-scoped `AsyncSession` (не создаёт свою через `session_factory()`) и не закрывает её в `__aexit__` — жизненный цикл сессии остаётся за FastAPI DI (`get_db_session`).

- **Rollback по умолчанию.** Если `commit()` не вызван явно (исключение, ранний `Result.error(...)`-возврат) — транзакция откатывается при выходе из `async with self.uow:`. Handler вызывает `await self.uow.commit()` только на успешном пути.
- **Репозитории не коммитят сами** — `session.commit()`/`_commit()` не встречается ни в одном мутирующем методе.
- **`drain_events_to_outbox(session, entity)` (см. [ADR 0010](0010-identity-service-event-integration.md)) — explicit-вызов в точке мутации репозитория**, не переезжает в `uow.commit()` и не становится автоматическим сбором из `session.new`/`session.dirty`.
- Кросс-сервисный UoW поверх нескольких БД не заводится: у каждого сервиса своя БД и своя `AsyncSession`; распределённая транзакция потребовала бы coordinator'а (2PC/saga), не рассматриваемого этим каноном.

## Пагинация: общий keyset-контракт в kernel-platform

Списочные query-хендлеры изменяемых сущностей используют keyset (cursor)-пагинацию, не `limit/offset`: при hard-delete между запросами соседних страниц `limit/offset` даёт «дрейф» (пропуск/задвоение элемента), тогда как курсор по конструкции устойчив к удалениям между запросами. Курсор — непрозрачный base64-токен, кодирующий позицию `(created_at, id)` последнего элемента страницы; страница не даёт `total`/номеров страниц — только `has_more`/`has_prev`, вычисляемые дешёвым overfetch (`limit + 1` строк).

Контракт живёт в `kernel_platform.pagination` (flat-модуль, только stdlib): `DEFAULT_PAGE_LIMIT`/`MAX_PAGE_LIMIT` (20/100), `InvalidCursorError`, `Cursor` (`created_at`, `id: uuid.UUID`), `PageInfo` (`next_cursor`/`prev_cursor`/`has_more`/`has_prev`), `encode_cursor`/`decode_cursor`. Каждый сервис, листающий изменяемую коллекцию, импортирует контракт отсюда напрямую — не держит собственной копии.

**Исключение — неизменяемые admin-only фиды (audit-логи).** Не подвержены дрейфу (только вставка, никогда не удаление/обновление) — используют `page_index`/`page_size` offset-пагинацию: она даёт дешёвый `total`/`total_pages`, которые курсор принципиально не предоставляет, а для admin-only фида это ценнее непрозрачности курсора.

## Considered Options

- **Repository-контракт в `application/`** — отклонено: делает `application` тем же «случайным владельцем» абстракции персистентности, каким мог бы стать любой другой слой; контракт персистентности агрегата логически принадлежит его собственному bounded context (domain), не первому потребителю.
- **Общий `ICommand`/`IQuery`, dispatcher, registry** — отклонено: три сервиса с небольшим числом сценариев каждый не оправдывают инфраструктуру pipeline-behavior; локальное соглашение о форме DTO даёт то же единообразие без лишнего слоя косвенности.
- **UnitOfWork с собственным `session_factory()`** — отклонено: завело бы вторую параллельную сессию на тот же HTTP-запрос и сломало бы транзакционную границу, которую уже задаёт FastAPI dependency lifecycle.
- **Commit по умолчанию вместо rollback по умолчанию** — отклонено: превращает забытый вызов `commit()` в тихую персистентную частичную мутацию — ровно тот класс бага, который UoW должен устранить.

## Consequences

- `check_architecture.py --strict` — единственный источник истины по направлению зависимостей и CQRS-границе для всех трёх сервисов, не ревью на глаз.
- Домен физически не может импортировать `httpx`/SQLAlchemy/OTEL иначе как через осознанное нарушение — граница держится на зависимостях `pyproject.toml` и на `check_architecture.py`.
- Handler, вызывающий 2+ мутирующих метода репозитория, атомарен: одна транзакция, один `uow.commit()` на успешном пути.
