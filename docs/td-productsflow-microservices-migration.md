# TD-01: Декомпозиция монолита ProductsFlow на микросервисы (Python 3.14) + highload-готовность и observability

Единый технический план. Объединяет две задачи: (1) распил монолита `ProductsFlow` на независимые микросервисы по DDD, (2) доведение до highload-готовности (кэш, отказоустойчивость, async, SLO) и подключение observability-стека (Prometheus/Loki/Tempo/Grafana) на чистом Docker.


Область — только backend (`app/`, `alembic/`, `tests/`, инфраструктура запуска). Клиент (`client/`) вне scope.

Ориентиры:
- Архитектурные подходы (слои, CQRS, Result/Error, Value Objects, Outbox, data-per-service) — из референса `Founder.TestTask` (C#/.NET). Из него берутся только приёмы, не бизнес-сущности.
- Принципы highload — из приложенной статьи: Design for failure, Stateless, Async by default, Cache everything, Measure everything, CQRS/read-replicas, Circuit Breaker / Timeout+Retry, три столпа observability.
- Конфиги мониторинга — адаптация стека (`grafana/loki/tempo/prometheus/minio/redis`) под Docker Compose.

Формат каждой фазы: **As-Is → To-Be → Шаги → DoD**. Переход к следующей фазе — только после закрытия DoD текущей.

---

## 1. Контекст (As-Is монолита)

`ProductsFlow` — зрелый монолит на FastAPI (один процесс, одна БД PostgreSQL, один деплой-юнит). Фактический стек: Python 3.14, FastAPI, Pydantic v2, SQLAlchemy 2.0 async + asyncpg, Alembic (миграции применяются на старте приложения), MinIO/S3 (`aioboto3`) для картинок товаров, JWT (`pyjwt`) + bcrypt, uv, pytest + testcontainers, ruff/mypy/vulture, Docker Compose (профили `dev`/`prod`), CI (GitHub Actions), ADR-документация (`docs/adr/0001..0009`).

Внутри монолита уже логически различимы три предметных области, размазанные по слою `router → repository → SQLAlchemy model` без выделенного domain-слоя:

- **Identity/RBAC** — `User` (регистрация, логин, роли `admin`/`user`, `is_active`, смена пароля, activate/deactivate), audit пользователей.
- **Catalog** — `Product` (CRUD, поиск/фильтры, keyset-пагинация, деактивация товара, featured, категории, картинки в S3), audit товаров.
- **Support** — обращения «пользователь ↔ админ» (`Conversation`/`ConversationMessage`), статусы, назначение админа, счётчики непрочитанного.

**Цель TD:** выделить эти области в независимые микросервисы, применив архитектурные подходы референса, сохранив всё зафиксированное в `CONTEXT.md`/ADR бизнес-поведение, и одновременно заложив highload-готовность и observability.

**Не цель:** смена бизнес-правил `User`/`Product`/`Support`; миграция dev-данных (сид генерируется на старте).

---

## 2. Инвентаризация домена (по факту кода)

### 2.1. Сущности и таблицы

| Сущность | Ключевые поля | Область |
|---|---|---|
| `User` | `id, username(unique,50), password_hash, role(admin/user), is_active, created_at, updated_at` | Identity |
| `UserAuditLog` | `id, user_id, actor_user_id, action(registered/password_changed/activated/deactivated), created_at` | Identity |
| `Product` | `id, name, category, price, description, user_id(FK→users), is_active, is_featured, created_at` | Catalog |
| `ProductImage` | `id, product_id(FK→products, unique, CASCADE), s3_key, content_type, size_bytes, created_at, updated_at` | Catalog |
| `ProductAuditLog` | `id, product_id(без FK — переживает delete), actor_user_id(FK→users), action(created/updated/deleted/activated/deactivated/image_updated/image_deleted), description, created_at` | Catalog |
| `Conversation` | `id, created_by_user_id(FK→users), subject, status(new/in_progress/closed), assigned_admin_id(FK→users), first_admin_reply_at, last_message_at, last_message_by_role, user_last_read_at, admin_last_read_at, closed_at, ...` | Support |
| `ConversationMessage` | `id, conversation_id(FK→conversations, CASCADE), sender_user_id(FK→users, SET NULL), sender_role, message(Text), created_at` | Support |

### 2.2. Ключевые бизнес-инварианты (из CONTEXT.md/ADR — сохраняются 1-в-1)

- **RBAC**: `admin` видит/меняет любые товары и учётки вне правил владения и видимости; обычный пользователь/аноним — по правилам видимости. `require_admin`, `ensure_owner_or_admin`, проверка владения на мутациях.
- **Аутентификация «мгновенной деактивации»**: `get_current_user`/`get_optional_current_user` (`app/security.py`) на каждый запрос перечитывают `is_active`/`role` из БД, а не доверяют JWT-payload. Деактивированный пользователь не проходит auth (`403`). Невалидный/просроченный/чужой токен НЕ откатывается на анонимный просмотр (ADR 0002).
- **Видимость товара** (ADR 0002/0003, CONTEXT.md): списки/поиск не персонализированы; деактивированный товар и товары деактивированного владельца скрыты от всех, кроме admin; исключение — прямой `GET /products/{id}` показывает владельцу его деактивированный товар.
- **Keyset-пагинация** по `(created_at, id)` для всех product-list (ADR 0001); offset-пагинация — только для admin-фида `GET /products/audit` (ADR 0005).
- **Audit trail** пишется декларативно через SQLAlchemy ORM event listeners (`app/audit.py`, ADR 0004), actor берётся из `ContextVar`, выставляемого HTTP-middleware из bearer-токена; исключение — мутации картинки (`IMAGE_UPDATED`/`IMAGE_DELETED`) пишутся явно, т.к. идут через raw SQL upsert (ADR 0009).
- **Картинка товара** (CONTEXT.md, ADR 0007/0008/0009): ≤1 на товар; upsert `INSERT ... ON CONFLICT (product_id) DO UPDATE`; стабильный S3-ключ `products/{id}/image`; публичная ссылка через отдельный `MINIO_PUBLIC_ENDPOINT`; видимость картинки производна от видимости товара; отдаётся только в `/api/v2`; общий seed-placeholder никогда не удаляется.
- **PATCH, не PUT** для частичного обновления товара (ADR 0006); `PUT` → 405.
- **Существование vs видимость** (CONTEXT.md): hard-delete товара; audit-лог переживает удаление; `404` «никогда не существовал» vs `403` «удалён» для не-admin — осознанное различие.
- **Support**: тикет видит только его создатель или любой admin; статусы `new/in_progress/closed`; трекинг `last_read_at` для непрочитанного; назначение админа.

### 2.3. Найденные технические долги (закрываем при миграции, не переносим as-is)

| # | Место | Проблема | Решение |
|---|---|---|---|
| 1 | `app/db.py` | `create_async_engine()` без параметров пула (`pool_size`/`max_overflow`/`pool_pre_ping`/`pool_recycle`) | Явная конфигурация пула на каждом сервисе |
| 2 | `settings.py`/`.env` | `SECRET_KEY`/`ADMIN_PASSWORD` пустые по умолчанию, старт без fail-fast | Валидация секретов в prod (fail-fast) |
| 3 | `app/logging_config.py` | Логи — цветной текст в stdout, не JSON; нет correlation-id; `uvicorn`/`sqlalchemy` не под единым форматом | Structured JSON logging + correlation (Фаза 8) |
| 4 | Весь `app/` | Нет метрик, трейсинга; `/health` плоский, не проверяет зависимости | Observability (Фазы 8–10) |
| 5 | `run_migrations()`+`seed_db()` в `lifespan` | Гонка при нескольких репликах (параллельный alembic upgrade и сид) | Вынести в one-off deploy-шаги (Фаза 11) |
| 6 | Везде | Кэша нет; горячие публичные read-пути бьют в Postgres на каждый запрос | Cache-Aside на Redis (Фаза 12) |
| 7 | `S3Storage` | Вызовы MinIO без таймаутов/retry/circuit breaker; `ensure_minio_buckets` в `lifespan` блокирует старт | Отказоустойчивость внешних зависимостей (Фаза 13) |
| 8 | `Product.user_id`, `Conversation.*_user_id` | Прямые FK между будущими сервисами в общей БД | Заменяются на локальные read-модели + события (§4) |

---

## 3. Что берём из `Founder.TestTask` (архитектура, не бизнес-логика)

| Подход референса | Аналог в Python-версии ProductsFlow |
|---|---|
| Clean Architecture `API → Application → Domain ← Infrastructure` | Слои `api/ application/ domain/ infrastructure/` в каждом сервисе |
| CQRS: явные Command/Query + Handler (MediatR) | `dataclass`-команды/запросы + функции-хендлеры вместо логики в `repository.py`/роутере |
| `Result<T>`/`Error`/`ErrorType` вместо `HTTPException` из глубины | `Result`/`Error` в `libs/common-kernel`, включая RBAC-ошибки; единый `problem()` в `api/` (аналог `ApiResults.Problem`) |
| Value Objects (`Inn`, `FullName`) | VO там, где есть реальный инвариант: `ProductPrice`(≥0), `Username`, `PasswordHash` |
| Доменные события → интеграционные события + Transactional Outbox | События `User`/`Product` через **честный** Outbox (в референсе Outbox отсутствовал — не переносим этот пробел) |
| Data-per-service + денормализация через события (`CustomerFounder`) | Локальные read-модели: `OwnerReadModel` в catalog, `UserRefReadModel` в support |
| Generic `IDefaultRepository<T>` + `IUnitOfWork` | `Repository[T]`/`UnitOfWork` поверх `AsyncSession` |
| `*Model`-суффикс ORM-сущностей | `UserModel`, `ProductModel`, `ProductImageModel`, `OwnerReadModel`, `ConversationModel` |

**Не переносим:** сущности `Founder`/`Customer`, MassTransit-специфику (в Python — `aio-pika`), отсутствие Outbox/idempotency в референсе.

---

## 4. Bounded contexts и межсервисная интеграция

| Сервис | Владеет | Своя БД | Зависит от |
|---|---|---|---|
| `identity-service` | `User`, `UserAuditLog`; выпуск/подпись JWT | `identity_db` | — |
| `catalog-service` | `Product`, `ProductImage`, `ProductAuditLog`; S3 картинок | `catalog_db` + свой MinIO-бакет | локальная read-копия пользователей |
| `support-service` | `Conversation`, `ConversationMessage` | `support_db` | локальная read-копия пользователей |

### 4.1. Авторизация между сервисами (ключевое решение)

Инвариант «деактивация действует немедленно» (§2.2) нужно сохранить, но catalog/support не могут ходить в БД identity на каждый запрос.

**Решение:**
1. `identity-service` подписывает JWT; для межсервисной проверки — **RS256** (рекомендация): приватный ключ только у identity, публичный раздаётся catalog/support для локальной проверки подписи без общего секрета. HS256 (общий секрет) — допустимая, но менее предпочтительная альтернатива; финальный выбор — за командой.
2. JWT удостоверяет личность (`user_id`), не является источником истины для `role`/`is_active`.
3. catalog и support держат локальные read-модели (`OwnerReadModel`, `UserRefReadModel`: `user_id, role, is_active`), обновляемые интеграционными событиями `user.registered.v1`/`user.activated.v1`/`user.deactivated.v1`/`user.role_changed.v1` (Outbox в identity + Idempotent Consumer, §5.1).
4. RBAC-проверки (`ensure_owner_or_admin`, видимость товара, доступ к тикету) выполняются локально по read-модели, без сетевого вызова identity. Плата — задержка применения деактивации = задержке доставки события (доли секунды), а не мгновенная, как в монолите. Это осознанный компромисс (CAP: выбираем доступность и слабую связанность). Если для конкретной write-операции нужна строгая согласованность — точечный синхронный fallback к identity; решение фиксируется в Фазе 7.

### 4.2. Связь `Product.user_id`

`user_id` товара перестаёт быть FK на таблицу пользователей (её больше нет в БД catalog). Владелец резолвится по `OwnerReadModel`. Правило видимости «товары деактивированного владельца скрыты» реализуется через `OwnerReadModel.is_active`, обновляемую событиями, а не JOIN на `users` (как сейчас в `repository.py`).

---

## 5. Целевая архитектура

```
ProductsFlow/
  libs/
    common-kernel/                 Result, Error, ErrorType, Entity, DomainEvent,
                                    Outbox/Inbox-примитивы, Repository/UnitOfWork,
                                    RBAC-политики, JWT-проверка, structured-logging,
                                    OTEL/metrics bootstrap (общий для всех сервисов)
  services/
    identity-service/
      identity_service/{api,application/{commands,queries},domain,infrastructure/{db,outbox,security}}
      alembic/  tests/{unit,integration}/  Dockerfile  pyproject.toml
    catalog-service/
      catalog_service/{api,application/{commands,queries,policies,consumers},domain,
                       infrastructure/{db,inbox,messaging,storage,security}}
      alembic/  tests/  Dockerfile  pyproject.toml
    support-service/
      support_service/{api,application/{commands,queries,consumers},domain,
                       infrastructure/{db,inbox,messaging,security}}
      alembic/  tests/  Dockerfile  pyproject.toml
  infra/
    gateway/                       nginx.conf (rate limit zones, quota via Redis/Lua,
                                    version routing /api/vN, CORS, JWT-verify, correlation)
    monitoring/{prometheus,loki,tempo,grafana/{provisioning,dashboards},promtail,alertmanager}/
  docker-compose.yml               gateway (nginx, единственный публичный порт),
                                    identity-{db,api,worker}, catalog-{db,api,worker},
                                    support-{db,api,worker}, rabbitmq, minio,
                                    prometheus, loki, tempo, grafana, promtail, redis
  Makefile   pyproject.toml (uv workspace root)
```

Слои внутри сервиса: `api/` — парсинг запроса + маппинг `Result`→HTTP (`problem()`); `application/` — команды/запросы/хендлеры/политики; `domain/` — чистые объекты, VO, инварианты, доменные события (без FastAPI/SQLAlchemy/Pydantic); `infrastructure/` — ORM, outbox/inbox, aio-pika, S3.

### 5.1. Асинхронная интеграция (Transactional Outbox & Idempotency)

**Проблема dual-write, которую закрываем.** Наивная схема «`commit` состояния в БД → затем `bus.publish` в RabbitMQ» — это две несогласованные операции над разными системами. Если процесс падает (или теряется сеть до брокера) в окне **между** успешным `commit` и `publish`, состояние в БД изменилось, а событие не отправлено — оно потеряно безвозвратно, и read-модели в catalog/support навсегда расходятся с identity. Обратный порядок (`publish` до `commit`) даёт зеркальную проблему — «фантомное» событие о непроизошедшем изменении. Гарантию даёт только запись факта-события в **ту же БД и ту же транзакцию**, что и само изменение агрегата — то есть Transactional Outbox.

**Механизм (identity как producer):**
1. Команда identity меняет агрегат `User` → поднимает доменное событие.
2. В **одной** транзакции `AsyncSession` атомарно фиксируются оба факта: изменение `UserModel` **и** вставка строки в `outbox_messages` (сериализованное тело события + метаданные). Либо коммитятся оба, либо ни один — окна рассинхронизации не существует.
3. Отдельный процесс `identity-worker` (Outbox Publisher) читает неопубликованные строки `outbox_messages` и публикует их в RabbitMQ (`aio-pika`). Это даёт гарантию **At-Least-Once**: если `publish` не удался или воркер упал до отметки «отправлено», строка остаётся неопубликованной и будет переотправлена — потеря невозможна, ценой возможных дублей.
4. `catalog-worker`/`support-worker` (Idempotent Consumer) проверяют `message_id` в `processed_messages`; новое — обрабатывают и обновляют read-модель в **той же** транзакции, что и вставку в `processed_messages`; дубль (следствие At-Least-Once) — ACK без повторной обработки.
5. Retry с Exponential Backoff, DLQ по исчерпании (в монолите messaging не было — закладываем сразу).

Реализация Outbox — отдельная под-фаза 2b (§7); здесь зафиксирован контракт, на который она опирается.

### 5.2. Обработка ошибок

Единый `problem()` в `api/`: `Result.Failure(Error)` → RFC7807 `ProblemDetails` (`Validation/Problem→400`, `NotFound→404`, `Conflict→409`, `Forbidden→403`, default→500). Существующие хендлеры `RequestValidationError`→422 (кастомный русскоязычный маппинг) и `IntegrityError`→409 переносятся почти как есть.

---

## 6. Принятые решения по scope

| Аспект | Решение |
|---|---|
| Runtime / менеджер / веб | Python 3.14, uv workspace, FastAPI + Uvicorn (как в монолите) |
| ORM / БД | SQLAlchemy 2.0 async + asyncpg, PostgreSQL, **своя БД на сервис** |
| Миграции | Alembic на каждый сервис; вынести из `lifespan` в deploy-шаг (Фаза 11) |
| Линт/типы | Ruff, `mypy --explicit-package-bases`, `vulture` (как в монолите, на каждый сервис) |
| Пароли | bcrypt — переносим как есть |
| JWT | RS256 (реком.), приватный ключ только у identity |
| Секреты | `.env`/секрет-менеджер, fail-fast в prod |
| Поиск/фильтры | `ILIKE`/`func.lower` (уже так в актуальном `repository.py`) |
| Пагинация | keyset для списков, offset для audit-фида — переносим (ADR 0001/0005) |
| Картинки | остаются в catalog (S3/MinIO), контракт `/api/v2` + `MINIO_PUBLIC_ENDPOINT` — переносим (ADR 0007/0008/0009) |
| Межсервисная связь | Outbox + локальные read-модели, не FK |
| Шина | RabbitMQ + `aio-pika`, явная топология + DLX |
| Кэш | Redis, Cache-Aside (Фаза 12) |
| Тестирование | pytest + testcontainers (Postgres + RabbitMQ) |
| Контейнеризация | Dockerfile на сервис + единый `docker-compose.yml` с профилями |
| API-шлюз | Nginx как единая точка входа: версионирование (`/api/vN`), rate limit, quota (через Redis), CORS, correlation-id (Фаза 7b) |
| Общий код | `libs/common-kernel` (editable через uv workspace), без пересечения доменов между собой |
| Observability | Prometheus + Loki + Tempo + Grafana на Docker (Фазы 8–10) |

---

## 7. Фазы реализации

### Фаза 0. Тулинг, каркас монорепо, common-kernel
**As-Is:** один пакет `app/`, общий `pyproject.toml`, пул БД не настроен, секреты без fail-fast.
**To-Be:** uv workspace c `services/*` и `libs/*`; общий kernel; заготовки сервисов собираются и линтятся.
**Шаги:**
- `uv` workspace root (`services/*`, `libs/*`).
- `libs/common-kernel`: `Result`/`Error`/`ErrorType` (+RBAC-ошибки), `Entity`, `IDomainEvent`, Outbox/Inbox-протоколы, `Repository`/`UnitOfWork`, JWT-verify (RS256), structured-logging bootstrap, OTEL/metrics bootstrap, конфиг пула БД (`pool_size/max_overflow/pool_pre_ping/pool_recycle`) и fail-fast-валидация секретов в prod.
- Пустые каркасы трёх сервисов + Dockerfile + базовый `alembic/`.
- CI: lint (ruff+mypy+vulture) + сборка пустых образов.
**DoD:** `make check` зелёный на всех сервисах и kernel; `docker compose build` собирает `identity-api`, `catalog-api`, `support-api`.

### Фаза 1. identity-service: домен + приложение
**As-Is:** `User`+RBAC размазаны по `security.py`/`repository.py`/`routers`, audit через ORM-события.
**To-Be:** выделенный домен `User` со всеми инвариантами; команды/запросы; unit-тесты.
**Шаги:**
- `domain/`: агрегат `User` (`Username`, `PasswordHash`, `Role`, `is_active`); события `UserRegistered/Activated/Deactivated/RoleChanged/PasswordChanged`.
- `application/`: `RegisterUserCommand`, `LoginCommand` (проверка `verify_password`), `ChangePasswordCommand` (проверка старого пароля), `ActivateUserCommand`, `DeactivateUserCommand` (запрет деактивации себя), `GetUserByIdQuery`, `ListUsersQuery`, audit-запросы пользователя.
- Unit-тесты: инварианты пароля (≥8, строчная, цифра), «нельзя деактивировать себя», RBAC.
**DoD:** unit-тесты зелёные; поведение `/auth/*` и `/users/*` (см. README) воспроизведено без изменений правил.

### Фаза 2. identity-service: инфраструктура, API, запись в Outbox
**As-Is:** одна БД, JWT HS256, миграции в lifespan.
**To-Be:** identity на своей БД, RS256; каждое доменное изменение атомарно фиксирует и состояние, и строку события в `outbox_messages` (без публикатора — он в Фазе 2b).
**Шаги:**
- `UserModel`+`UserAuditLog`, Alembic, PostgreSQL, пул из kernel.
- bcrypt (as-is), выпуск JWT RS256; приватный ключ только здесь; audit через ORM-события (перенос `app/audit.py` в части User).
- FastAPI `/api/v1/auth/*`, `/api/v1/users/*` (сохранить контракт README, включая `/users/*/audit`).
- Таблица `outbox_messages`; вставка события (`user.registered/activated/deactivated/role_changed.v1`) в **той же транзакции**, что и мутация агрегата (единый `AsyncSession`/UnitOfWork из kernel) — гарантия, что изменение и факт-событие коммитятся атомарно.
**DoD:** identity поднимается на реальном Postgres; register→login→change-password→activate/deactivate end-to-end; интеграционный тест подтверждает, что каждое изменение агрегата и соответствующая строка `outbox_messages` появляются атомарно (при откате транзакции — нет ни того, ни другого).

### Фаза 2b. Transactional Outbox Publisher + Idempotent Consumer
**As-Is:** событий в шину пока не уходит (Фаза 2 только пишет их в БД); наивная схема «`commit` → затем `publish`» дала бы потерю событий при сбое между коммитом и публикацией (окно dual-write, §5.1).
**To-Be:** события гарантированно доставляются из `outbox_messages` в RabbitMQ (At-Least-Once) и идемпотентно применяются потребителями; потеря события при сбое между commit и publish структурно невозможна.
**Шаги:**
- В `libs/common-kernel` — переиспользуемые примитивы Outbox/Inbox (модель `outbox_messages`: `id, aggregate_type, event_type, payload, occurred_at, published_at, attempts`; модель `processed_messages`: `message_id, processed_at`) и базовый Publisher/Consumer, общие для всех сервисов-producer'ов и consumer'ов.
- `identity-worker` (отдельный процесс/compose-сервис, не HTTP-воркер): периодически (polling или `LISTEN/NOTIFY`) выбирает строки с `published_at IS NULL`, публикует в RabbitMQ через `aio-pika` (`aio-pika` publisher confirms), проставляет `published_at`. Строка помечается опубликованной только после подтверждения брокера — сбой на любом шаге оставляет её неопубликованной → безопасная переотправка (At-Least-Once).
- Явная топология RabbitMQ: exchange (`topic`), очереди, routing keys `user.*.v1`, DLX + Dead-Letter Queue; retry с Exponential Backoff; лимит попыток → DLQ.
- Idempotent Consumer в consumer-сервисах (реализуется в Фазах 4/5): проверка `message_id` в `processed_messages` до обработки; применение эффекта и вставка `processed_messages` — в одной транзакции; дубль (следствие At-Least-Once) → ACK без повтора.
- Метрики (заготовка под Фазу 9): размер невыгруженного outbox (лаг публикации), возраст самой старой неопубликованной строки, счётчики publish/retry/DLQ.
- Тесты (testcontainers Postgres + RabbitMQ): (а) craш между `commit` и публикацией — после рестарта воркера событие всё равно доезжает (нет потери); (б) двойная доставка одного `message_id` не создаёт дублей в read-модели; (в) «отравленное» сообщение уходит в DLQ после исчерпания retry.
**DoD:** событие, зафиксированное в `outbox_messages`, доезжает до RabbitMQ даже при рестарте identity/воркера в момент публикации; повторная доставка идемпотентна; исчерпание retry маршрутизирует сообщение в DLQ; на дашборде (после Фазы 9) виден лаг outbox.

### Фаза 3. catalog-service: домен + приложение
**As-Is:** `Product` + видимость + featured + категории + картинки + audit в общем `repository.py`.
**To-Be:** выделенный домен `Product`; политики видимости и владения как переиспользуемые компоненты; unit-тесты.
**Шаги:**
- `domain/`: агрегат `Product` (VO `ProductPrice`≥0), `ProductImage`, `OwnerRef` (read-сущность: `role`, `is_active`); доменные события `ProductCreated/Updated/Deleted/Activated/Deactivated`.
- `application/`: команды `CreateProduct/UpdateProduct(PATCH)/DeleteProduct/ActivateProduct/DeactivateProduct/UpsertProductImage/DeleteProductImage`; запросы `ListProducts(keyset)/SearchProducts/ByCategory/ByPriceRange/GetById/GetFeatured/GetCategoriesWithCount/ProductAudit(offset)`; политики `visibility` (ADR 0002/0003) и `owner_or_admin` в `application/policies/`.
- Audit товаров: ORM-события (перенос `app/audit.py` для Product) + явная запись для image-мутаций (ADR 0009).
- Unit-тесты на все ветки видимости, владения, keyset-курсор, image-upsert.
**DoD:** unit-тесты зелёные; поведение всех `/products/*` (README) и `/api/v2` image/categories сохранено 1-в-1, кроме замены JOIN-на-users правил видимости на `OwnerRef`.

### Фаза 4. catalog-service: инфраструктура, API, S3, интеграция identity
**As-Is:** видимость строится JOIN на `users`; картинки в общем MinIO; consumer'ов нет.
**To-Be:** catalog на своей БД + своём бакете; owner-данные из read-модели; consumer событий identity.
**Шаги:**
- `ProductModel`/`ProductImageModel`/`ProductAuditLog`/`OwnerReadModel`, Alembic, PostgreSQL, индексы под горячие фильтры (`category`, `price`, `(is_active, created_at, id)`, `user_id`).
- Перенос `S3Storage` (aioboto3), контракт `/api/v2` картинок, `MINIO_PUBLIC_ENDPOINT` (ADR 0007/0008/0009).
- FastAPI `/api/v1/products/*` + `/api/v2/products/{id}/image`, `/api/v2/categories`.
- JWT-проверка публичным ключом identity (локально), опциональная auth (ADR 0002) через kernel.
- `aio-pika` consumer `user.*.v1` → `OwnerReadModel`; `catalog-worker` (Idempotent Consumer, `processed_messages`).
**DoD:** регистрация/деактивация пользователя в identity отражается в `OwnerReadModel` без прямого вызова API; повторная доставка не создаёт дублей; видимость товаров деактивированного владельца работает по read-модели; картинки отдаются по контракту v2.

### Фаза 5. support-service
**As-Is:** `Conversation`/`ConversationMessage` в общем монолите, FK на `users`, доступ через `CurrentUser`/`AdminUser`.
**To-Be:** support на своей БД, доступ по локальной `UserRefReadModel`, consumer identity-событий.
**Шаги:**
- `domain/`: `Conversation` (статусы `new/in_progress/closed`, назначение админа, трекинг непрочитанного), `ConversationMessage`, `UserRef`.
- `application/`: команды создания обращения/сообщения, назначения админа, смены статуса, отметки прочтения; запросы списков (пользовательских и админских), счётчиков (`SupportCounts`), треда сообщений.
- `infrastructure/`: `ConversationModel`/`ConversationMessageModel`/`UserRefReadModel`, Alembic, индексы (перенос `ix_conv_status_admin`, `ix_conv_messages_history`); `support-worker` consumer `user.*.v1`.
- FastAPI `/api/v1/support/*` (user) и `/api/v1/admin/support/*` (admin) — сохранить контракт.
- Доступ к тикету: создатель-или-admin по `UserRefReadModel`.
**DoD:** пользователь видит только свои обращения, admin — все; счётчики/непрочитанное корректны; удаление пользователя в identity корректно отражается (SET NULL-семантика через событие).

### Фаза 6. Интеграционное и контрактное тестирование
**As-Is:** тесты монолитные (`tests/unit`, `tests/integration` на testcontainers одной БД).
**To-Be:** межсервисные E2E на реальных Postgres×3 + RabbitMQ.
**Шаги:**
- `testcontainers`: 3×Postgres + RabbitMQ (+ MinIO для catalog).
- E2E: `register user → login → create product → deactivate user → событие → OwnerReadModel/UserRefReadModel обновлены → товары скрыты, тикеты недоступны`.
- Контрактные тесты HTTP: сверка статусов/тел с README и ADR (keyset-курсоры, 405 на PUT, 404 vs 403 для удалённого товара, видимость).
**DoD:** сквозной сценарий зелёный; покрытие критичных доменных/application-слоёв по заданному порогу (`pytest --cov`).

### Фаза 7. Готовность к горизонтальному масштабированию (Stateless)
**As-Is:** `run_migrations()`+`seed_db()` в `lifespan` каждого инстанса — гонка при репликах; `seed_db` генерирует 360 товаров + грузит placeholder на старте.
**To-Be:** реплики любого сервиса стартуют без гонок; миграции/сид вынесены из рантайма.
**Шаги:**
- Вынести `alembic upgrade head` в one-off compose-сервис `*-migrations` (`depends_on: db healthy`), API стартует после него.
- `seed` — отдельная идемпотентная команда с `pg_advisory_lock`, не в каждом старте prod-реплики.
- В compose — пример `--scale *-api=N` (убрать `container_name`), nginx как upstream-балансировщик перед репликами (SSL termination, gzip, `least_conn`, `keepalive` к upstream). Rate limit / quota / маршрутизация версий выносятся в отдельный шлюз — Фаза 7b.
- `/health/ready` (Фаза 9) управляет включением реплики в балансировку.
- Зафиксировать решение по строгой согласованности деактивации (§4.1): eventual по умолчанию, синхронный fallback точечно при необходимости.
**DoD:** `docker compose up --scale catalog-api=3` — 3 реплики без конфликта миграций/сида; nginx распределяет; readiness-гейт работает.

### Фаза 7b. HTTP API-шлюз на Nginx: rate limit, quota, версионирование
**Статус: частично реализовано** (issue #282, срез #284) — единый Nginx-шлюз (`backend/infra/gateway/nginx.conf`, Compose-сервис `gateway`) существует и является единственной публикуемой точкой входа в dev/prod (`/api/v1/*` маршрутизация на реальные upstream-пути, JSON 404 на нераспознанный путь, `/healthz` для healthcheck); подробности — [ADR 0004](adr/0004-api-gateway-and-routing.md), [ADR 0001](adr/0001-platform-topology-and-bounded-contexts.md). Rate limiting и anti-spoofing заголовков/`X-Request-ID` — отдельные срезы этой же эпопеи (issue #285, #286). Остальное ниже остаётся нереализованным и годится как кандидаты на отдельные issue:
- Quota (Redis/Lua/OpenResty, лимиты в сутки/месяц на пользователя или ключ).
- CORS на шлюзе (сервисы пока сохраняют собственный `CORSMiddleware`).
- Версионирование через `regex + map` под будущий `/api/vN` (пока нет ни одного `/api/v2`, добавлять негде).
- Метрики nginx (`stub_status`/`nginx-prometheus-exporter`) и интеграция с Prometheus.
- JSON-формат логов nginx для Loki/Promtail.

**As-Is:** после распила каждый сервис публикует свой порт напрямую; единой точки входа нет. Маршрутизация версий сейчас живёт внутри монолита (`/api/v1`, `/api/v2` — ADR 0007), CORS настроен в приложении (`CORSMiddleware` из `settings.cors_allow_origins`). Rate limiting, квот и защиты от всплесков трафика нет ни на одном уровне — любой клиент может залить публичные list/search-эндпоинты (перегрузка Postgres, отсутствие backpressure — «Design for failure» из статьи не покрыт на входе).
**To-Be:** единый Nginx-шлюз перед всеми сервисами — терминирует TLS, маршрутизирует по версии и домену, ограничивает частоту и объём запросов (rate limit + quota), проставляет correlation-id и передаёт identity вниз, отдаёт стандартные 429/503 при перегрузке.

**Шаги:**

*Версионирование и маршрутизация*
- Единый `infra/gateway/nginx.conf` — вся внешняя поверхность за одним `server{}`; апстримы `identity_api`, `catalog_api`, `support_api` (`upstream{}` с несколькими репликами из Фазы 7).
- Маршрутизация по URI-версии (сохранить текущий контракт, не ломать клиентов):
  - `/api/v1/auth/*`, `/api/v1/users/*` → `identity_api`;
  - `/api/v1/products/*`, `/api/v2/products/*`, `/api/v2/categories/*` → `catalog_api`;
  - `/api/v1/support/*`, `/api/v1/admin/support/*` → `support_api`.
- Версия — только в пути (`/api/vN/...`), как уже принято в ADR 0007; заголовочное/媒-type версионирование не вводим (консистентность с существующим контрактом). Задел на будущие версии: числовой `location ~ ^/api/v(\d+)/` + `map` версии → апстрим, чтобы добавление `/api/v3` не требовало переписывания всех `location`.
- Депрекация версий: на ответах устаревающей версии добавлять заголовки `Deprecation: true` и `Sunset: <дата>` через `add_header` в соответствующем `location` — без изменения кода сервисов.
- CORS перенести с приложения на шлюз (единая точка): `add_header Access-Control-Allow-*` + обработка preflight `OPTIONS` на уровне nginx; в приложениях `CORSMiddleware` оставить только для локального dev-запуска без шлюза.

*Rate limiting (частота)*
- `limit_req_zone` с ключом по клиенту. Ключ — многоуровневый через `map`: для аутентифицированных — по `user_id` (см. ниже про проброс), для анонимных — по `$binary_remote_addr` (при работе за внешним LB/CDN — по `X-Forwarded-For` с `real_ip`/`set_real_ip_from`).
- Разные зоны и лимиты по классам эндпоинтов (не один лимит на всё):
  - `zone=auth`: жёсткий лимит на `/api/v1/auth/login` и `/register` (анти-brute-force, напр. 5–10 r/m + `burst` малый, `nodelay` выкл.);
  - `zone=write`: умеренный на мутации (`POST/PATCH/DELETE` товаров, отправка сообщений support);
  - `zone=read_public`: более щедрый на публичные list/search (`GET /products/*`);
  - каждый `location` подключает свою зону через `limit_req ... burst=... [nodelay]`.
- `limit_conn_zone`/`limit_conn` — ограничение одновременных соединений на клиента (защита slow-loris и параллельного выкачивания).
- Ответ при срабатывании — `429 Too Many Requests` с `Retry-After` (`limit_req_status 429;`); тело — RFC7807-совместимый JSON (единый формат ошибок с приложением, §5.2), отдаётся через `error_page 429 = @ratelimited`.

*Quota (объём за период)*
- Nginx из коробки не считает суточные/месячные квоты — только мгновенную частоту. Для квот («N запросов в сутки на пользователя/ключ», «M загрузок картинок в час») — Nginx + Lua (OpenResty) или `njs`: счётчик в Redis (тот же, что для кэша, Фаза 12) по ключу `quota:{user_id|api_key}:{период}` с TTL, инкремент на входе, отказ `429`/`403 Quota Exceeded` при превышении. Возвращать заголовки `X-RateLimit-Limit`/`X-RateLimit-Remaining`/`X-RateLimit-Reset`.
- Тарифные классы квот — через `map` роли/плана (напр. `anon` / `user` / `admin` / будущие платные планы) на разные лимиты; роль берётся из проброшенного identity-контекста (ниже).
- Альтернатива без Lua на первом этапе: квоты считать в приложении (identity выдаёт лимит в claims токена, сервисы проверяют счётчик в Redis) — шлюз тогда отвечает только за rate limit; выбор Lua-vs-app зафиксировать как решение до реализации.

*Идентичность и correlation через шлюз*
- Шлюз генерирует/пробрасывает `X-Request-ID` (совпадает с correlation-id из Фазы 8), чтобы трейс/лог начинался на входе.
- Опционально: валидация JWT на шлюзе (`auth_request` к легковесному endpoint identity или Lua-проверка подписи публичным ключом RS256, §4.1) и проброс `X-User-Id`/`X-User-Role` вниз — тогда rate-limit-ключ и quota знают пользователя. Инвариант «мгновенная деактивация» (§4.1) при этом сохраняется на стороне сервисов (перечитывание `is_active`), шлюз лишь ускоряет типовой отказ; финально валидация авторитетно остаётся в сервисах.
- Скрыть внутренние заголовки от клиента и наоборот: очищать входящие `X-User-*` от клиента (анти-spoofing), чтобы их нельзя было подделать в обход шлюза.

*Инфраструктура*
- `gateway` — сервис в `docker-compose.yml` (профиль `prod`), единственный публикующий порт наружу (`80/443`); сервисы `*-api` больше не пробрасывают порты на хост (только внутренняя сеть).
- `healthcheck` шлюза; `nginx -t` в CI (валидация конфига); зона `limit_req` с разумным `10m`-размером.
- Метрики nginx (`stub_status` или `nginx-prometheus-exporter`) → Prometheus (Фаза 9): активные соединения, счётчики 429/5xx, upstream latency.
- Логи nginx — в JSON (`log_format`), совместимо с Loki/Promtail (Фаза 11), с полями `request_id`, `limit_req_status`, upstream.

**DoD:** весь внешний трафик идёт через один Nginx-порт; `/api/v1`/`/api/v2` корректно маршрутизируются по сервисам без изменения клиентского контракта; превышение частоты на `/auth/login` отдаёт `429` с `Retry-After`; превышение суточной квоты пользователя отдаёт `429`/`403` с `X-RateLimit-*`; депрекация версии видна в заголовках `Deprecation`/`Sunset`; поддельные `X-User-*` от клиента отбрасываются; метрики шлюза (429/5xx/upstream latency) видны в Grafana.


### Фаза 8. Structured logging + correlation ID
**As-Is:** `app/logging_config.py` — цветной текст в stdout, не JSON; нет request-id/trace-id; `contextvar current_actor_id` только для audit.
**To-Be:** все сервисы пишут structured JSON в stdout с общими полями и correlation.
**Шаги (в `libs/common-kernel`, применяется всеми сервисами):**
- JSON-форматтер (поля `timestamp, level, logger, message, service, request_id, trace_id, span_id, actor_id, method, path, status_code, duration_ms`); цветной вывод — только `APP_ENV=dev`.
- `contextvar` `request_id` из заголовка `X-Request-ID` (иначе `uuid4`), возврат тем же заголовком; access-log одной структурной записью на запрос (свой middleware, `uvicorn --no-access-log`).
- Проброс `request_id`/`actor_id`/`trace_id` в каждую запись через `logging.Filter`/contextvars.
- Уровни: `sqlalchemy.engine=WARNING` в prod (echo — только dev).
**DoD:** каждая строка — валидный JSON; по `request_id` связываются все записи одного запроса во всех сервисах; в dev остаётся читаемый вывод.

### Фаза 9. Метрики (Prometheus) + health
**As-Is:** метрик нет; `/health` плоский, не проверяет зависимости; `MINIO_PROMETHEUS_AUTH_TYPE=public` уже выставлен.
**To-Be:** каждый сервис экспонирует `/metrics` (RED + инфраструктурные); `/health` разделён на live/ready.
**Шаги:**
- `prometheus-fastapi-instrumentator` (или `prometheus_client`) → `GET /metrics` в каждом сервисе.
- RED по HTTP (`http_requests_total`, `http_request_duration_seconds` histogram, `http_requests_in_progress`); USE по пулу БД (`checkedout/checkedin/overflow`); латентность S3 (catalog), RabbitMQ publish/consume, DLQ-счётчики, размер outbox (лаг публикации).
- Бизнес-метрики: `products_created_total`, `auth_login_failures_total`, `audit_events_total{entity,action}`, `support_open_conversations`.
- `GET /health/live` (процесс) и `GET /health/ready` (`SELECT 1` + для catalog `head_bucket` MinIO + доступность RabbitMQ, с таймаутом). `/metrics` и `/health/*` — вне access-лога и вне RED-гистограмм.
**DoD:** `curl /metrics` отдаёт per-route latency и метрики пула/шины; readiness краснеет при недоступности Postgres/RabbitMQ/MinIO.

### Фаза 10. Distributed tracing (OpenTelemetry → Tempo)
**As-Is:** трейсинга нет; латентность SQL/S3/RabbitMQ не разложима, особенно на межсервисных цепочках через шину.
**To-Be:** сквозной trace HTTP → SQLAlchemy → aioboto3 → RabbitMQ (context propagation между сервисами); `trace_id`/`span_id` в JSON-логах.
**Шаги:**
- OTEL SDK + автоинструментация `fastapi`/`sqlalchemy`/`asyncpg`/`botocore`/`aio-pika`, экспортёр OTLP gRPC на Tempo `:4317`.
- Конфиг env: `OTEL_EXPORTER_OTLP_ENDPOINT`, `OTEL_SERVICE_NAME` (per-service), сэмплинг в prod (`parentbased_traceidratio`).
- Пропагация trace-context через RabbitMQ-заголовки (identity outbox → catalog/support consumer), чтобы трейс не рвался на шине.
- Инжект `trace_id`/`span_id` в logging-контекст (Фаза 8).
**DoD:** в Tempo виден сквозной трейс `register user → publish → consume → OwnerReadModel updated` со спанами БД/шины; из строки лога в Loki по `trace_id` открывается трейс.

### Фаза 11. Стек мониторинга на чистом Docker (адаптация k8s-референса)
**As-Is:** приложенные конфиги `grafana/loki/tempo/prometheus/minio/redis` — под Kubernetes (`Namespace`, `PV/PVC` hostPath, `StatefulSet/Deployment`, `Service ClusterIP/LoadBalancer` + `nodePort`, `Secret`, `initContainers` chown, DNS `*.monitoring.svc.cluster.local`). В текущем `docker-compose.yml` уже есть MinIO и бакеты `loki-chunks`/`tempo-traces` в `.env` — заготовка под Loki/Tempo на S3 заложена, но сервисов мониторинга нет.
**To-Be:** полный observability-стек поднимается через `docker compose` (без k8s), переиспользует MinIO как S3-backend Loki/Tempo, подключён к сети сервисов.

**Правила трансляции k8s → Docker Compose:**

| k8s-примитив | Docker Compose эквивалент |
|---|---|
| `Namespace: monitoring` | compose-сеть `monitoring` (+ подключить `*-api` к ней) |
| `PersistentVolume`/`PVC` (hostPath) | named `volumes:` (`prometheus_data`, `grafana_data`, `loki_data`, `tempo_data`) |
| `ConfigMap` (`*.yml`, `grafana.ini`, `redis.conf`) | bind-mount из `infra/monitoring/<svc>/` |
| `Secret` (`stringData`) | `.env` + `env_file`/`environment` |
| `initContainers` chown | не нужны (том принадлежит контейнеру; при необходимости `user:`) |
| `Service ClusterIP` + FQDN `svc.cluster.local` | обращение по имени compose-сервиса (`prometheus`, `loki`, `tempo`, `minio`) |
| `Service LoadBalancer` + `nodePort` | проброс `ports:` на хост |
| `readiness/livenessProbe` | `healthcheck:` |
| `resources requests/limits` | `deploy.resources.limits` (опционально) |
| `remote_write http://prometheus:9090/...` | тот же URL — имя compose-сервиса `prometheus` |

**Шаги:**
- `infra/monitoring/{prometheus,loki,tempo,grafana/{provisioning/datasources,provisioning/dashboards,dashboards},promtail,alertmanager}/`.
- `prometheus.yml`: таргеты `*.svc.cluster.local` → compose-имена; убрать `checkenterprises`; добавить джобы `identity-api:8000`/`catalog-api:8000`/`support-api:8000` (`/metrics`), `tempo:3200`, `minio:9000` (`/minio/v2/metrics/cluster`+`/bucket`), `prometheus`. Флаги как в референсе: `--storage.tsdb.retention.time=7d`, `--retention.size=3GB`, `--web.enable-remote-write-receiver`, `--enable-feature=exemplar-storage,native-histograms`.
- `loki/local-config.yml`: из референса; `s3.endpoint` → `minio:9000`, `s3forcepathstyle/insecure=true`, `${MINIO_*}` через `-config.expand-env=true`; `INSTANCE_ADDR=127.0.0.1` (вместо `status.podIP`); `ring.kvstore: inmemory` (single-node); ретеншн по уровням сохранить.
- `tempo/tempo.yml`: `otlp grpc :4317`; `storage.trace.s3` → `minio:9000` бакет `${MINIO_BUCKET_NAME_TEMPO}`; `metrics_generator.remote_write` → `http://prometheus:9090/api/v1/write`; Redis-кэш — только если поднимаем Redis (Фаза 12/13).
- `grafana`: убрать `root_url/serve_from_sub_path` (k8s-ingress); provisioning файлами: datasources (Prometheus/Loki/Tempo с `derivedFields` Loki→Tempo по `trace_id` и `tracesToLogs` Tempo→Loki) + дашборды (RED по каждому сервису, USE пула БД, панель MinIO, лаг outbox/DLQ, логи Loki, трейсы Tempo).
- `promtail` (или Alloy): читает Docker-логи контейнеров, пушит в Loki; т.к. логи уже JSON (Фаза 8) — только `json`-stage + label `service`/`level`, без regex.
- Профиль `monitoring` в compose (по аналогии с `dev`/`prod`): `docker compose --profile prod --profile monitoring up`; `*-api` дополнительно в сети `monitoring`.
- `healthcheck` каждого сервиса (Grafana `/api/health`, Loki `/ready`, Prometheus `/-/ready`, Tempo `/ready`, MinIO `/minio/health/live`).
- Секреты (`GF_SECURITY_ADMIN_PASSWORD`, `MINIO_*`, `REDIS_PASSWORD`) — через `.env`, дополнить `.env.example`.
**DoD:** `docker compose --profile prod --profile monitoring up -d` поднимает сервисы + postgres×3 + minio + rabbitmq + prometheus + loki + tempo + grafana + promtail; в Grafana преднастроены datasource и дашборды; видны RED-метрики, логи Loki и трейсы Tempo; переход лог→трейс по `trace_id` работает.

### Фаза 12. Производительность read-путей (кэш, сжатие, отдача)
**As-Is:** кэша нет; публичные list/search (`/products/*`) бьют в Postgres на каждый запрос; keyset-пагинация уже есть; gzip и `Cache-Control`/`ETag` не настроены.
**To-Be:** горячие публичные read-пути кэшируются (Cache-Aside/Redis), ответы сжимаются и кэшируемы на HTTP-уровне.
**Шаги:**
- Redis (адаптация `redis.yaml` референса в compose, профиль `cache`/`monitoring`): `redis.conf` bind-mount, `requirepass`, `appendonly yes`, named volume.
- Cache-Aside в catalog для публичных read: ключ по нормализованным параметрам (`category`/`price-range`/`cursor`/`limit`), TTL 30–60 c, версионирование ключей (`products:v{N}:...`); явная инвалидация по мутациям товара.
- Anti-stampede: single-flight lock или probabilistic early expiration.
- `GZipMiddleware` (или gzip на nginx) для ответов > N байт; `Cache-Control`/`ETag` на публичные неперсонализированные списки (подтверждено ADR 0002).
- Проверить/добавить индексы под фильтры (Фаза 4), EXPLAIN на list/search (index scan, не seq scan).
**DoD:** повторный публичный list обслуживается из Redis (метрика hit-rate на дашборде); ответы сжимаются; на горячих фильтрах index scan; мутация товара инвалидирует кэш.

### Фаза 13. Отказоустойчивость внешних зависимостей
**As-Is:** вызовы MinIO без таймаутов/retry/circuit breaker; `ensure_minio_buckets` в `lifespan` блокирует старт; таймаутов на БД-операции нет; graceful degradation отсутствует.
**To-Be:** каждый внешний вызов с таймаутом; transient-сбои переживаются retry+backoff; устойчивые — размыкают circuit breaker с деградацией; старт не висит на недоступной зависимости.
**Шаги:**
- `botocore.config.Config(connect_timeout, read_timeout, retries=adaptive)` для `S3Storage`; circuit breaker вокруг S3 → при open деградация: товар отдаётся без `image_url`, а не 5xx.
- `ensure_minio_buckets` — с таймаутом и не-фатально в dev; в prod вынести в one-off сервис (как миграции, Фаза 7).
- БД: `pool_pre_ping` (Фаза 0) + `command_timeout` asyncpg; retry на transient-connection для идемпотентных чтений.
- RabbitMQ consumer: retry+backoff → DLQ (§5.1); circuit breaker на consumer-pipeline против DLX-шторма.
- Redis-кэш — необязательная зависимость: недоступность → fallback в БД, не ошибка.
**DoD:** при остановленном MinIO list/детали товара отдаются без картинки (200, `image_url=null`); сервисы стартуют при недоступных MinIO/Redis; на дашборде виден статус circuit breaker.

### Фаза 14. Async by default: вынос тяжёлых операций
**As-Is:** audit синхронный в транзакции (ок); тяжёлые побочные эффекты (S3-операции, обработка картинок, уведомления support) — синхронно в HTTP-запросе; брокер уже есть для интеграции (§5.1).
**To-Be:** некритичные к немедленному ответу побочные эффекты — в фон; тяжёлые операции не держат HTTP-воркер.
**Шаги:**
- Побочные эффекты (пост-обработка картинки, инвалидация распределённого кэша, уведомления support) — в фон: `BackgroundTasks`, при росте — отдельный worker + очередь.
- Транзакционная гарантия доменных событий — тем же Outbox (§5.1), а не «опубликовать после commit».
- Внешний I/O в фоне — с теми же таймаутами/breaker (Фаза 13).
**DoD:** загрузка картинки отвечает, не дожидаясь необязательной пост-обработки; `http_requests_in_progress` на этих ручках не растёт.

### Фаза 15. SLI/SLO, алертинг, нагрузочное тестирование
**As-Is:** SLO не определены, алертов и нагрузочного тестирования нет; функциональные тесты есть.
**To-Be:** определены SLI/SLO, настроены алерты по симптомам, базовая нагрузка сверяется с SLO.
**Шаги:**
- SLI/SLO (по образцу статьи): список товаров p99 < 200 ms; `POST /products` success > 99.5%; readiness > 99.9%; доставка события identity→read-модель < N c.
- Prometheus recording rules (p95/p99) + alerting rules (5xx-rate, latency-burn, насыщение пула, лаг/рост outbox и DLQ, недоступность readiness, circuit breaker open).
- `alertmanager` в compose-стек `monitoring` (`infra/monitoring/alertmanager/config.yml`), Prometheus с `--alerting`; error-budget-панели в Grafana.
- Нагрузочные сценарии `k6`/`locust` (публичный list/search, `POST /products`, login, отправка сообщения support) против compose-стека; nightly/`workflow_dispatch`; k6 `thresholds` = SLO; экспорт в Grafana (remote-write).
**DoD:** искусственная деградация поднимает алерт в Alertmanager; nightly-нагрузка публикует latency/RPS в Grafana; регресс латентности валит порог.

---

## 8. Верификация

- `make check` — зелёный на трёх сервисах и `libs/common-kernel`.
- `make test service=<svc>` — зелёные; `make coverage` — покрытие критичных слоёв.
- `docker compose --profile prod --profile monitoring up --build` — поднимает весь стек (nginx-gateway + 3 сервиса + 3 воркера + 3 Postgres + RabbitMQ + MinIO + Redis + Prometheus/Loki/Tempo/Grafana/Promtail/Alertmanager). Наружу публикует порт только gateway.
- Функционально: `register → login → create product (owner из токена) → GET /products (keyset) отражает товар → deactivate user → товар исчезает из публичной выдачи и его тикеты недоступны → в Grafana виден сквозной trace и логи по request_id`.

---

## 9. Риски и стратегии смягчения

| Риск | Смягчение |
|---|---|
| Eventual consistency деактивации (в монолите — мгновенно) | §4.1: осознанный компромисс; синхронный fallback точечно для строгих write-операций; решение в Фазе 7 |
| Общий секрет JWT при HS256 | Реком. RS256, приватный ключ только у identity; HS256 — только через защищённое хранилище |
| Разрыв FK `Product.user_id`/`Conversation.*_user_id` → «осиротевшие» строки | identity не делает hard-delete пользователя (только `is_active=false`); support использует SET NULL-семантику через событие |
| **Потеря событий при сбое между commit и publish** (dual-write) | **Transactional Outbox** (§5.1, Фаза 2b): изменение агрегата и строка `outbox_messages` коммитятся в одной транзакции; отдельный Publisher доставляет из БД в RabbitMQ с At-Least-Once (publisher confirms, переотправка неопубликованных); Idempotent Consumer (`processed_messages`) гасит дубли; исчерпание retry → DLQ. Никогда не публикуем в шину до успешного COMMIT. В референсе `Founder.TestTask` Outbox отсутствовал — этот пробел не переносим, а закрываем |
| Имена RabbitMQ exchange/queue могут быть завязаны на внешних потребителей | Проверить перед Фазой 4/5; явная топология `aio-pika`, согласование имён |
| Слепой перенос C#-приёмов без переосмысления под Python | `common-kernel` проектируется под FastAPI/Python (Depends вместо DI-контейнера), берём принцип, не код |
| k8s-конфиги мониторинга содержат k8s-специфику (PV/PVC, LoadBalancer, FQDN) | §Фаза 11: явная таблица трансляции + пофайловая адаптация |
| Гонка миграций/сида при репликах | Вынос из `lifespan` в one-off сервисы + `pg_advisory_lock` (Фаза 7) |
| Кэш даёт устаревшие данные | TTL + явная инвалидация по мутациям + версионирование ключей; кэш — необязательная зависимость |
| Overhead 3 Postgres + RabbitMQ + Redis + мониторинг для среднего домена | Осознанный компромисс TD (цель — отработать highload-микросервисную архитектуру), зафиксирован как решение |
| Nginx-шлюз — единая точка отказа (SPOF) и потенциальное «бутылочное горло» | Шлюз stateless (счётчики квот — в Redis, не в nginx) → масштабируется несколькими репликами за внешним LB/DNS; таймауты/`proxy_next_upstream` к апстримам; healthcheck; при недоступности Redis для квот — fail-open на quota, но rate limit (in-nginx) продолжает работать |
| Rate limit/quota по IP бьёт по пользователям за общим NAT/CDN | Ключ лимита — по `user_id` для аутентифицированных (проброс из JWT), по IP — только для анонимных; `real_ip`/`X-Forwarded-For` при работе за CDN/LB; тарифные классы через `map` роли/плана |
| Подмена `X-User-*`/версии клиентом в обход шлюза | Шлюз затирает входящие `X-User-*` от клиента; сервисы авторитетно перепроверяют JWT и `is_active` сами (§4.1), не доверяя заголовкам шлюза для критичных решений |
