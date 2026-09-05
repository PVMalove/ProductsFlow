# 0001. Топология платформы, точки входа и границы контекстов

**Статус:** Accepted

## Топология

Платформа состоит из трёх независимо разворачиваемых микросервисов и общего, не разворачиваемого самостоятельно Shared Kernel:

| Компонент          | Роль                                                                                                                                                                                                                    |
|--------------------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `identity-service` | Владеет учётной записью (`User`), выпускает и подписывает JWT, единственный источник истины о личности и роли                                                                                                           |
| `catalog-service`  | Владеет товаром (`Product`), публичной витриной, картинками товаров                                                                                                                                                     |
| `support-service`  | Владеет обращениями в поддержку (`Ticket`, `TicketMessage`)                                                                                                                                                             |
| `kernel-domain`    | Библиотека без внешних зависимостей: `Result`/`Error`, `Entity`, `DomainEvent`, `VisibilityPolicy` — импортируется доменом каждого сервиса напрямую                                                                     |
| `kernel-platform`  | Библиотека инфраструктурных портов: HTTP-конверт и обработка ошибок, `Actor`/RBAC, `IdentityClient`, Outbox/`UnitOfWork`, keyset-пагинация — импортируется слоями `api`/`application`/`infrastructure`, никогда доменом |
| `observability`    | Structured logging, request-context middleware — самодостаточная библиотека, выделенная из `kernel-platform`                                                                                                            |
| `test-support`     | Dev-only testcontainers-фикстуры, общие для интеграционных тестов трёх сервисов                                                                                                                                         |

Каждый сервис — собственный процесс, собственная база данных (`identity-db`/`catalog-db`/`support-db`), собственный Alembic, собственный Docker-образ. Данные между сервисами не расшариваются напрямую ни через общую БД, ни через прямой SQL — единственный канал межсервисной интеграции — события через RabbitMQ (детали — cross-service ADR каждого сервиса, 0010–0012).

## Точки входа

**Dev — единая точка входа через Nginx Gateway.** Клиент (включая BFF-фронтенд) обращается к сервисам через один Nginx-шлюз (`backend/infra/gateway/nginx.conf`, Compose-сервис `gateway` в `backend/docker-compose.yml`), который маршрутизирует по текущему `/api/v1/*` контракту на соответствующий сервис. В dev-профиле `gateway` — единственный сервис, публикующий порт наружу (`docker-compose.dev.yml`: `8080:80`); `identity-api`/`catalog-api`/`support-api` порты на хост в dev больше не пробрасывают. Полное описание — [ADR 0004](0004-api-gateway-and-routing.md).

**Prod пока не переключён.** `backend/docker-compose.prod.yml` не тронут этим решением: `identity-api`/`catalog-api`/`support-api` по-прежнему публикуют `9013`–`9015`, а `gateway` (унаследованный из базового `docker-compose.yml`) в prod-профиле не публикует порт вовсе. Перевод prod на единую точку входа через `gateway` — отдельное решение (issue #289).

**Nginx-Gateway для E2E — отдельная, не связанная с dev/prod инфраструктура** (`docker-compose.e2e.yml`, `backend/tests/e2e/nginx.conf`) — session-scoped, поднимается и уничтожается pytest-фикстурой на время прогона E2E-сценариев, использует собственный конфиг и динамический порт, не является частью боевой топологии. Стратегия его использования в тестах — [ADR 0013](0013-testing-strategy.md).

## Безопасный старт

Ни один сервис не выполняет миграции Alembic или сидирование БД внутри `lifespan` FastAPI — один код-путь без ветвления по `APP_ENV`, во избежание гонки нескольких реплик API и блокировки старта HTTP-сервера миграцией. Каждый сервис имеет one-off bootstrap-шаг (`identity-bootstrap`/`catalog-bootstrap`/`support-bootstrap`): `alembic upgrade head` → (только catalog) `ensure_minio_buckets` → сид, последовательно; `*-api`/`*-worker` стартуют только после `service_completed_successfully` своего bootstrap-шага. Три bootstrap-шага не зависят друг от друга.

`catalog-bootstrap` дискаверит id сидированного admin-пользователя не по фиксированной конвенции, а поллингом собственной `OwnerReadModel`-таблицы (`wait_for_admin_user_id`) — сидированный admin реально проходит event-driven путь `user.registered.v1` → `identity-worker` → `catalog-worker` → `OwnerReadModel`, потому что `users.id` — GUID (см. [ADR 0006](0006-service-internal-architecture-baseline.md)), не автоинкремент, и никакой предсказуемой конвенции id не существует.

`make setup` поднимает `*-db`/MinIO/RabbitMQ и прогоняет миграции всех трёх сервисов без сида; `make demo` (`setup` как prerequisite) добавляет сид-шаг и поднимает `identity-worker`/`catalog-worker` на время, необходимое поллингу `catalog-bootstrap`. `support-worker` в `make demo` не поднимается — сид support (пустая таблица `Ticket`, connectivity-check) от проекции не зависит.

## Границы контекстов (Bounded Contexts)

- **Identity** — учётная запись, аутентификация, роль. Единственный владелец правды о `is_active`/`role`; остальные сервисы читают её только через события ([ADR 0010](0010-identity-service-event-integration.md)–[0012](0012-support-service-event-integration.md)), никогда напрямую из чужой БД.
- **Catalog** — товар, его видимость, картинка. Владеет собственной проекцией пользователя (`OwnerReadModel`) для нужд видимости, не владеет самим понятием пользователя.
- **Support** — обращение, сообщение, жизненный цикл тикета. Владеет собственной проекцией пользователя (`user_projection`) для аутентификации и владения тикетом.

Контексты не пересекаются по данным: у каждого своя таблица `users`-подобной проекции, синхронизируемая исключительно событиями identity, а не общим схема-владением. Синхронизация — предмет [ADR 0010](0010-identity-service-event-integration.md)–[0012](0012-support-service-event-integration.md); правила видимости внутри контекста — предмет [ADR 0007](0007-identity-service-domain-model.md)–[0009](0009-support-service-domain-model.md).
