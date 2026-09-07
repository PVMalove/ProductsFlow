# ProductsFlow

[![CI](https://github.com/PVMalove/ProductsFlow/actions/workflows/ci.yml/badge.svg)](https://github.com/PVMalove/ProductsFlow/actions/workflows/ci.yml)
![Python 3.14](https://img.shields.io/badge/python-3.14-blue)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

ProductsFlow — распределённая микросервисная платформа для учёта товаров. Архитектура построена на принципах предметно-ориентированного проектирования (DDD), событийно-ориентированного взаимодействия (EDA) и гексагональной архитектуры (Ports & Adapters).

Проект организован по принципу Polyrepo в рамках одного репозитория: три независимо разворачиваемых сервиса, каждый со своим `pyproject.toml`. Зависимости резолвятся в один общий `backend/uv.lock` и `backend/.venv` (общий workspace), что необходимо для E2E-тестов.

Полная архитектурная документация: [ADR-база](docs/adr/README.md) (13 решений, от топологии до стратегии тестирования) и [`docs/architecture/backend_architecture.md`](docs/architecture/backend_architecture.md) (диаграммы и пояснения к ней).

## Что реализовано

- **CQRS и тонкие роутеры** во всех трёх сервисах — HTTP-обработчик строит command/query, вызывает один handler, транслирует `Result` в ответ; direction-of-dependency и разделение command/query проверяются автоматически (`make -C backend architecture-check`).
- **BFF-конверт ответа** (`{"data": ..., "meta": {}}` / `{"error": {"code": ..., "message": ...}}`) — единый для всех бизнесовых эндпоинтов, включая списки, картинку товара и audit-фиды.
- **GUID-идентификаторы** — все агрегаты используют `uuid.UUID`, без предсказуемых инкрементов.
- **Unit of Work** — транзакционная граница command handler'а с rollback по умолчанию; репозитории не коммитят сами.
- **Transactional Outbox + событийная хореография** — `identity-service` публикует события о пользователе через RabbitMQ; `catalog-service` и `support-service` строят собственные локальные проекции (`OwnerReadModel`, `user_projection`) вместо синхронных вызовов на каждый запрос.
- **Безопасный старт** — миграции и сидирование вынесены в одноразовые bootstrap-контейнеры, не в `lifespan` FastAPI.
- **Изолированное тестирование** — юнит/интеграционные тесты внутри каждого сервиса, плюс общий чёрный ящик E2E через изолированный Nginx-Gateway (только для тестов, см. ниже).

## Топология

Сервисы **не имеют общих баз данных** и не импортируют код друг друга. **Единая точка входа — Nginx Gateway**: и в dev (`8080:80`), и в prod (`80:80`) это единственный сервис, публикующий порт наружу; `identity-api`/`catalog-api`/`support-api` порты на хост не пробрасывают ни в одном из профилей. Отдельно от него — изолированная E2E-тестовая инфраструктура (свой Nginx-Gateway), поднимаемая и уничтожаемая pytest-фикстурой на время прогона.

![Макро-архитектура: клиент → Gateway → три изолированных сервиса, каждый со своей БД и общим RabbitMQ, catalog дополнительно синхронно ходит в identity; все три сервиса используют Shared Kernel (kernel-domain, kernel-platform, observability); MinIO переиспользуется opt-in LGTM Monitoring оверлеем](docs/architecture/diagrams/macro-architecture.png)

[Открыть интерактивную схему](docs/architecture/diagrams/macro-architecture.html) (pan/zoom, переключение темы, трассировка связей — открывать локально в браузере, GitHub не рендерит HTML из репозитория; подробности по воркерам — [backend_architecture.md §3](docs/architecture/backend_architecture.md)).

- **`identity-service`** — учётные записи, ролевая модель (`user`/`admin`), выдача stateless JWT (RS256), единственный producer доменных событий.
- **`catalog-service`** — товары, видимость, картинки (MinIO); проверяет JWT через JWKS-кэш (`IdentityClient`) и делает синхронный добор к identity на холодном старте read-модели и на админской ветке.
- **`support-service`** — тикеты поддержки; проверяет JWT статическим публичным ключом из своей конфигурации (без сети к identity), deny-by-default вместо синхронного добора.

Разделяемый код — в `backend/libs/` (path-зависимости, без semver, HEAD-версии):
- `kernel-domain` — без сторонних зависимостей: `Result`/`Error`, `Entity`, `DomainEvent`, `VisibilityPolicy`.
- `kernel-platform` — BFF-конверт и обработка ошибок, `Actor`/RBAC, `IdentityClient`, transactional Outbox + `UnitOfWork`, keyset-пагинация.
- `observability` — structured logging, `RequestContextMiddleware`, OpenTelemetry SDK (трейсинг + Prometheus-метрики) во всех API/worker-процессах; `trace_id`/`span_id` в логе — реальные, а не зарезервированные `null` (см. раздел «Наблюдаемость» ниже).
- `test-support` — dev-only testcontainers-фикстуры для интеграционных тестов.

## Устройство одного сервиса

![Устройство одного сервиса: FastAPI Routers/RabbitMQ Consumer → Command/Query Handlers → Entities/Repository Ports → SQL Repository, направление зависимостей строго внутрь](docs/architecture/diagrams/micro-architecture.png)

[Открыть интерактивную схему](docs/architecture/diagrams/micro-architecture.html) (pan/zoom, переключение темы, трассировка связей — открывать локально в браузере, GitHub не рендерит HTML из репозитория).

## Стек технологий

- **Python 3.14**, **FastAPI**, **Pydantic v2**
- **SQLAlchemy 2.0** (async), **Alembic** (изолированные миграции на сервис)
- **PostgreSQL** — своя логическая БД на сервис
- **RabbitMQ** + Transactional Outbox (гарантия At-Least-Once, без синхронного двойного write)
- **MinIO** (S3-совместимое хранилище: приватные картинки товаров через presigned URL; в opt-in monitoring overlay — ещё и чанки/блоки Loki и Tempo)
- **JWT (PyJWT, RS256)** — issuer identity; **bcrypt** — хеширование паролей
- **uv** — общий workspace (`backend/uv.lock` и `backend/.venv`) для всех пакетов (`libs/*`, `services/*`)
- **pytest**, **ruff**, **mypy**, `check_architecture.py` (CQRS/direction-of-dependency gate)
- **Docker Compose** + GitHub Actions (матрица CI по пакетам)
- **OpenTelemetry** (трейсинг + Prometheus-метрики) во всех API/worker-процессах; **Prometheus + Loki + Promtail + Tempo + Grafana** — opt-in Compose overlay поверх этого же стека ([ADR 0015](docs/adr/0015-observability-and-asynchronous-trace-propagation.md), раздел «Наблюдаемость (LGTM overlay, опционально)» ниже)

Structured JSON-логирование подключено с первого дня; в API-процессах (`*-api`) оно опционально переключается в единый JSON-формат с `trace_id` — специально для monitoring overlay, чтобы Loki мог связать лог с трейсом в Tempo.

## Быстрый старт

Требуется [uv](https://docs.astral.sh/uv/), `make`, `Docker`. Все команды выполняются из `backend/`.

```bash
cd backend
cp .env.example .env
# отредактируйте .env — как минимум задайте IDENTITY_JWT_PRIVATE_KEY_PATH и ADMIN_PASSWORD

make keys                  # сгенерировать dev-пару ключей RS256 для identity

# собрать все образы приложений (по умолчанию с Docker-кэшем)
make build
# при необходимости полностью пересобрать без кэша:
# make build no_cache=1

make setup                 # поднять *-db + MinIO + RabbitMQ, прогнать миграции (без сида и без API)
make demo                  # setup + сид (админ, демо-товары) + воркеры

make up_dev                # поднять все *-api и *-worker в dev-профиле (Gateway :8080, API :9013–9015)
```

`make demo` уже включает `make setup`, поэтому обычно достаточно одного из
сценариев:

- без демо-данных: `make build` → `make up_dev`;
- с демо-данными: `make build` → `make demo` → `make up_dev`.

Для полной пересборки в любом сценарии используйте `make build no_cache=1`.
Если нужно собрать только один сервис, добавьте `service`, например:
`make build service=catalog-api no_cache=1`.

Swagger UI сервисов доступен через Gateway и по прямым dev-портам:

- identity-service: http://localhost:9013/docs
- catalog-service: http://localhost:9014/docs
- support-service: http://localhost:9015/docs

## Наблюдаемость (LGTM overlay, опционально)

Локальный стек Prometheus + Loki + Promtail + Tempo + Grafana — opt-in Compose overlay поверх уже поднятого backend-стека (ADR 0015; более подробная схема потоков данных — [backend_architecture.md §5.3](docs/architecture/backend_architecture.md)). Использует существующий MinIO как S3-хранилище Loki/Tempo и отдельный `monitoring-redis` как кэш поиска трейсов Tempo; ничего не публикует наружу кроме Grafana. Своего Make-таргета намеренно нет — запускается явной командой:

![Схема LGTM-оверлея: три независимых потока (метрики/логи/трейсы) от identity/catalog/support сходятся в Grafana](docs/architecture/diagrams/observability-lgtm-overlay.png)

[Открыть интерактивную схему](docs/architecture/diagrams/observability-lgtm-overlay.html) (pan/zoom, переключение темы, трассировка связей — открывать локально в браузере, GitHub не рендерит HTML из репозитория).

```bash
cd backend
docker compose -f docker-compose.yml -f docker-compose.dev.yml -f docker-compose.monitoring.yml up -d
```

Grafana — http://localhost:3300 (логин/пароль по умолчанию `admin`/`admin`, переопределяются `GRAFANA_ADMIN_USER`/`GRAFANA_ADMIN_PASSWORD`).

**Смоук-проверка** (подтверждает связку HTTP-запрос → Loki-лог → Tempo-трейс):

```bash
curl -X POST http://localhost:8080/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"smoke@example.test","password":"Smoke-Test-Pass-123"}'
```

1. В Grafana → Explore → Loki: `{compose_service="identity-api"}` — найти строку `POST /api/v1/auth/register` и её JSON-поле `trace_id`.
2. По этой же строке кликнуть derived-field-ссылку «Открыть трейс в Tempo» (или открыть трейс по `trace_id` напрямую в Explore → Tempo).
3. В трейсе должны быть: HTTP-спан `POST /api/v1/auth/register` (identity-service), `publish_message` (identity-worker, Outbox-паблишер) и `consume_message` (catalog-worker/catalog-search-worker/support-worker — все три консьюмера `user.registered.v1`).

Остановить оверлей (данные в томах и в MinIO сохраняются):

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml -f docker-compose.monitoring.yml stop prometheus loki tempo promtail grafana
```

## Тестирование

Тесты запускаются изолированно по пакетам — свой `uv`-run, но единое окружение:

```bash
cd backend
make test pkg=identity-service
make test pkg=catalog-service
make test pkg=support-service
make test pkg=kernel-domain
make architecture-check          # CQRS-аудит + направление зависимостей
```

### Межсервисное E2E Тестирование (Black-box Pipeline)
  
  Пайплайн сквозного (End-to-End) тестирования проверяет систему целиком, как "черный ящик", обращаясь исключительно через единый тестовый Nginx API Gateway. Внутреннее взаимодействие проверяется асинхронно через RabbitMQ, валидируя итоговую консистентность всей распределенной архитектуры.
  
  Запуск (`session-scoped` окружение):
  ```bash
  uv run --project tests/e2e pytest tests/e2e
  ```
  
  В пайплайне реализованы 3 глобальных сценария:
  
  **1. Проверка доменных правил видимости (Catalog)**
  (`test_owner_keeps_direct_access_to_deactivated_product`)
  Проверяет многопользовательскую изоляцию и видимость товаров.
  - Регистрируются два независимых пользователя: `Owner` and `Viewer`.
  - `Owner` создает товар (публично доступен).
  - `Owner` деактивирует товар (меняет статус `is_active=False`).
  - Проверка: `Owner` по-прежнему видит свой товар (HTTP 200), а для `Viewer` этот же URL отдаёт HTTP 404 (товар скрыт от посторонних).
  
![Деактивированный товар остаётся виден Owner (200), но скрыт от Viewer (404)](docs/architecture/diagrams/e2e-product-visibility.png)

[Открыть интерактивную схему](docs/architecture/diagrams/e2e-product-visibility.html) (pan/zoom, переключение темы, трассировка связей — открывать локально в браузере, GitHub не рендерит HTML из репозитория).
  
  **2. Защита периметра (API Gateway)**
  (`test_gateway_denies_a_path_outside_its_allow_list`)
  Гарантирует, что Nginx API Gateway выступает надежным барьером и не пропускает неавторизованные пути наружу.
  - Имитируется запрос к внутренней системной ручке (например, `/internal/health`).
  - Gateway обязан заблокировать запрос (HTTP 404) до того, как он дойдет до микросервисов.
  
  **3. Межсервисная Хореография (Identity → RabbitMQ → Support)**
  (`test_self_delete_anonymizes_and_closes_the_users_ticket`)
  Тестирует распределенную Event-Driven архитектуру. Проверяет, что удаление пользователя в одном микросервисе корректно транслируется и обрабатывается в другом.
  - Пользователь регистрируется и создает обращение (тикет) в `support-service`.
  - Пользователь удаляет свой профиль (`DELETE /users/me` в `identity-service`).
  - `identity-service` под капотом публикует событие `user.deleted.v1` в RabbitMQ.
  - Воркер службы поддержки ловит событие, анонимизирует автора тикета (заменяя ID на `null`), переводит тикет в `CLOSED` и оставляет системное сообщение.
  - Тест авторизуется под Администратором и поллит API поддержки, ожидая подтверждения, что тикет закрыт и анонимизирован.
  
![Самоудаление пользователя: identity публикует user.deleted.v1 в RabbitMQ, support-worker асинхронно анонимизирует и закрывает тикет пользователя](docs/architecture/diagrams/e2e-choreography.png)

[Открыть интерактивную схему](docs/architecture/diagrams/e2e-choreography.html) (pan/zoom, переключение темы, трассировка связей — открывать локально в браузере, GitHub не рендерит HTML из репозитория).
  Подробности E2E инфраструктуры — в [ADR 0013](docs/adr/0013-testing-strategy.md).

## Переменные окружения

Полный список — `backend/.env.example`. Основные:

| Переменная | Назначение |
| --- | --- |
| `APP_ENV` | `dev`/`prod` |
| `IDENTITY_DATABASE_URL` / `CATALOG_DATABASE_URL` / `SUPPORT_DATABASE_URL` | Строки подключения — своя БД на сервис |
| `IDENTITY_JWT_PRIVATE_KEY_PATH` | Путь к приватному RS256-ключу (только identity; `make keys` сгенерирует dev-пару) |
| `IDENTITY_ACCESS_TOKEN_TTL_HOURS` | Время жизни access-токена |
| `IDENTITY_AMQP_URL` / `CATALOG_AMQP_URL` / `SUPPORT_AMQP_URL` | Подключение к RabbitMQ |
| `CATALOG_IDENTITY_BASE_URL` | Базовый URL identity для `IdentityClient` (JWKS + синхронный добор) |
| `MINIO_ENDPOINT` / `MINIO_PUBLIC_ENDPOINT` | Внутренний и внешний адрес MinIO |
| `ADMIN_EMAIL` / `ADMIN_PASSWORD` | Сидируемый администратор |

## Интерфейсы и Доменные операции

Проект построен по принципу слабой связанности (Loose Coupling): каждый микросервис обслуживает свой домен через REST API на собственном порту. Все идентификаторы сущностей в системе — `UUIDv4`. Ответы API стандартизированы под единую оболочку (BFF Envelope: `data`, `meta`, `error`).

### 1. Identity Service (Управление пользователями)
Отвечает за аутентификацию, безопасность и жизненный цикл аккаунтов. Выступает единым источником правды для JWT-ключей (JWKS).
* **Аутентификация:** Регистрация, вход по логину/паролю и выдача асимметричных токенов (RS256 JWT).
* **Профиль:** Получение данных текущего пользователя (`users/me`), смена пароля.
* **Администрирование:** Выдача админских прав, принудительная блокировка/разблокировка пользователей (влияет на доступ во всех остальных сервисах).
* **Удаление:** Необратимое удаление аккаунта (`DELETE /api/v1/users/me`). Данные в базе физически заменяются анонимизированным "надгробием" (tombstone), а в RabbitMQ (через Transactional Outbox) уходит глобальное событие `user.deleted.v1`.

### 2. Catalog Service (Управление товарами)
Управляет жизненным циклом товаров, витриной и медиа-вложениями.
* **Публичная витрина:** Оптимизированная курсорная пагинация (keyset) списков товаров. Видимость каждого товара высчитывается на лету из трёх независимых правил: статус товара (`is_active`), статус владельца и права запрашивающего.
* **CRUD Товара:** Создание, идемпотентное частичное обновление (`PATCH`), активация/деактивация (меняет видимость для публики) и полное удаление.
* **Управление медиа:** Прямой изоляции с MinIO. Файлы хранятся в приватных bucket'ах, а клиенту отдаются исключительно временные защищенные presigned-ссылки для скачивания/загрузки.
* **Admin Audit:** Лента истории изменения товаров администраторами.
* **Хореография:** Воркер слушает события от Identity (в т.ч. `user.deleted.v1`) и обновляет локальную кэш-таблицу `owner_read_model`. Если пользователь удален — все его товары немедленно скрываются с витрины.

### 3. Support Service (Служба поддержки)
Обработка обращений, жалоб и взаимодействие с клиентами.
* **Жизненный цикл тикета:** Строгая конечная автомат-модель статусов: `OPEN` → `IN_PROGRESS` → `RESOLVED` → `CLOSED` (терминальный статус).
* **Треды (Переписка):** Оставление сообщений внутри тикета. Реализовано мягкое удаление (Soft Delete) сообщений: текст стирается, но карточка сообщения сохраняет позицию в треде для целостности истории.
* **Хореография:** По событию `user.deleted.v1` из шины, сервис анонимизирует ссылку на автора в его тикетах и сообщениях, а также принудительно переводит все его активные тикеты в статус `CLOSED` с системным уведомлением.

## Лицензия

[MIT](LICENSE)
