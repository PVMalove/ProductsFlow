# Детализированная Архитектура Backend-приложения

Данный документ описывает устройство микросервисного бэкенда (`backend/`). Архитектура базируется на принципах изолированного предметно-ориентированного проектирования (DDD), событийно-ориентированного взаимодействия (EDA) и гексагональной архитектуры. Схемы оптимизированы для **тёмной темы**.

---

## 1. Глоссарий и Базовые Концепции

*   **Polyrepo (в рамках Monorepo):** Архитектурный подход, при котором независимые сервисы лежат в одном репозитории, но имеют строго изолированные виртуальные окружения (через `uv`) и файлы блокировок (`uv.lock`). Исключает "ад зависимостей".
*   **DDD (Domain-Driven Design):** Проектирование, отталкивающееся от бизнес-процессов. Бизнес-логика ядра не зависит от фреймворков и баз данных.
*   **Clean / Hexagonal Architecture (Ports and Adapters):** Разделение на слои, где зависимости направлены исключительно внутрь (к Domain). Внешние системы (БД, API, RabbitMQ) общаются с ядром через строго заданные интерфейсы (Порты).
*   **Aggregate Root:** Главная сущность кластера связанных объектов. Мутации внутри кластера происходят только через неё, обеспечивая транзакционную целостность.
*   **Outbox Pattern:** Решение проблемы "двойной записи" (Dual Write). Доменные события сохраняются в таблицу БД в одной транзакции с бизнес-данными, а фоновый воркер (Relay) гарантированно отправляет их в брокер.
*   **Идемпотентность:** Способность обработчика событий безопасно принимать одно и то же сообщение несколько раз без дублирования эффектов (необходимо из-за гарантии доставки At-Least-Once в RabbitMQ).
*   **API Gateway:** Единая точка входа для клиентов. Занимается маршрутизацией HTTP-запросов, SSL-терминацией и ограничением частоты запросов (Rate Limiting).

---

## 2. Топология Workspace-репозитория

```text
backend/
├── Makefile                     # Единый Task Runner (маршрутизация команд в нужные пакеты)
├── pyproject.toml               # Глобальные настройки линтеров (ruff, mypy, pytest)
│
├── infra/                       # Инфраструктура
│   ├── docker-compose.yml       # Локальный стенд (Postgres, RabbitMQ, Redis)
│   └── gateway/                 # Конфигурация API Gateway (nginx / traefik / envoy)
│
├── libs/                        # Shared Kernel (Общие контракты и инструменты)
│   ├── kernel-domain/           # Базовые абстракции (Entity, AggregateRoot, DomainEvent)
│   ├── kernel-platform/         # Инфра-адаптеры (Outbox, JWT Validators, AMQP Consumers)
│   └── observability/           # Настройка OpenTelemetry (Трейсы, Метрики, Логи)
│
└── services/                    # Независимые микросервисы
    ├── identity-service/        
    │   ├── alembic/             # Изолированные миграции
    │   ├── src/identity/        # Исходный код (по слоям Clean Arch)
    │   └── pyproject.toml       # Локальные зависимости сервиса
    ├── catalog-service/         # Управление товарами/инвентарем
    └── support-service/         # Система тикетов и обратной связи
```

---

## 3. Макро-Архитектура (Межсервисное взаимодействие)

Сервисы **не имеют общих баз данных** и не импортируют код друг друга. Внешние клиенты общаются с системой через API Gateway. Синхронные межсервисные вызовы сведены к минимуму во избежание каскадных сбоев.
```mermaid
%%{init: {'theme': 'dark'}}%%
graph TD
    Client(["Mobile / Web Clients"])
    GW{"API Gateway<br/>(Traefik / Nginx)"}
    
    Client -->|HTTPS| GW

    subgraph "Polyrepo Workspace (backend/)"
        direction TB
        
        subgraph "Independent Microservices"
            IS["identity-service<br/>(Auth, Users)"]
            CS["catalog-service<br/>(Products)"]
            SS["support-service<br/>(Tickets)"]
        end

        subgraph "Shared Packages (libs/)"
            KD["kernel-domain"]
            KP["kernel-platform"]
            OBS["observability"]
        end
        
        IS -. "uses" .-> KD & KP & OBS
        CS -. "uses" .-> KD & KP & OBS
        SS -. "uses" .-> KD & KP & OBS
    end
    
    GW -->|REST / HTTP| IS
    GW -->|REST / HTTP| CS
    GW -->|REST / HTTP| SS

    subgraph "Infrastructure Layer"
        DB[("PostgreSQL<br/>(Logical DBs)")]
        MQ(("RabbitMQ<br/>(Event Bus)"))
        OTEL[["OpenTelemetry<br/>(Jaeger/Prometheus)"]]
    end

    IS --> DB & MQ & OTEL
    CS --> DB & MQ & OTEL
    SS --> DB & MQ & OTEL

    style Client fill:#1f2937,stroke:#9ca3af,color:#fff
    style GW fill:#0f766e,stroke:#2dd4bf,color:#fff
    style IS fill:#1e3a8a,stroke:#60a5fa,color:#fff
    style CS fill:#1e3a8a,stroke:#60a5fa,color:#fff
    style SS fill:#1e3a8a,stroke:#60a5fa,color:#fff
    style KD fill:#14532d,stroke:#4ade80,color:#fff
    style KP fill:#14532d,stroke:#4ade80,color:#fff
    style OBS fill:#14532d,stroke:#4ade80,color:#fff
    style DB fill:#7c2d12,stroke:#fb923c,color:#fff
    style MQ fill:#7c2d12,stroke:#fb923c,color:#fff
    style OTEL fill:#4c1d95,stroke:#a78bfa,color:#fff
```

---
## 4. Микро-Архитектура (Устройство отдельного сервиса)

Организация кода внутри сервиса (например, `identity-service`) строго следует правилу инверсии зависимостей. 
```mermaid
%%{init: {'theme': 'dark'}}%%
graph TD
    subgraph "Service Boundary"
        direction TB
        
        subgraph "1. Presentation (Primary Adapters)"
            Routers["FastAPI Routers"]
            Schemas["Pydantic DTOs"]
            AMQPConsumer["RabbitMQ Consumers"]
        end
        
        subgraph "2. Application (Use Cases)"
            Commands["Command Handlers<br/>(Mutations)"]
            Queries["Query Handlers<br/>(Reads)"]
        end
        
        subgraph "3. Domain (Core)"
            Entities["Aggregates & Entities"]
            Events["Domain Events"]
            Ports["Repository Interfaces<br/>(Abstract Base Classes)"]
        end
        
        subgraph "4. Infrastructure (Secondary Adapters)"
            Repos["SQLAlchemy Repositories"]
            Models["ORM Models"]
            ExternalAPI["External HTTP Clients"]
        end
        
        Routers --> Commands & Queries
        AMQPConsumer --> Commands
        
        Commands --> Entities
        Commands --> Ports
        
        Repos -. "Implements" .-> Ports
        Repos --> Models
    end
    
    style Routers fill:#1e3a8a,stroke:#60a5fa,color:#fff
    style AMQPConsumer fill:#1e3a8a,stroke:#60a5fa,color:#fff
    style Commands fill:#4c1d95,stroke:#a78bfa,color:#fff
    style Queries fill:#4c1d95,stroke:#a78bfa,color:#fff
    style Entities fill:#14532d,stroke:#4ade80,color:#fff
    style Ports fill:#14532d,stroke:#4ade80,color:#fff
    style Repos fill:#7c2d12,stroke:#fb923c,color:#fff
```

### Доменная модель и Наследование
```mermaid
%%{init: {'theme': 'dark'}}%%
classDiagram
    class AggregateRoot {
        <<kernel-domain>>
        -list _domain_events
        +add_event(event)
        +pull_events() list
    }
    
    class OutboxMixin {
        <<kernel-platform>>
        +UUID event_id
        +String event_type
        +JSONB payload
        +DateTime processed_at
    }
    
    class User {
        <<identity-service>>
        +UUID id
        +String email
        +String password_hash
        +change_password(new_pwd)
        +deactivate()
    }
    
    AggregateRoot <|-- User : Наследует шину событий
    OutboxMixin <|-- OutboxModel : Наследует SQL-структуру
    User ..> UserDeactivatedEvent : Генерирует при мутациях
```

---

## 5. Потоки Данных (Взаимодействие)

### 5.1. Stateless JWT Авторизация (Локальная проверка)

При проверке прав доступа микросервисам не нужно делать HTTP-запрос в `identity-service`. Они используют публичный ключ для криптографической валидации подписи.
```mermaid
%%{init: {'theme': 'dark'}}%%
sequenceDiagram
    autonumber
    actor C as Client
    participant GW as API Gateway
    participant IS as identity-service
    participant CS as catalog-service
    participant KP as kernel-platform (Security)
    
    C->>GW: POST /auth/login
    GW->>IS: Проксирование запроса
    rect rgb(30, 58, 138)
        IS-->>C: 200 OK + JWT (Подписан RS256 Private Key)
    end
    
    C->>GW: GET /catalog/my-products (Bearer JWT)
    GW->>CS: Проксирование запроса
    
    rect rgb(20, 83, 45)
        note over CS,KP: Быстрая локальная валидация (без сети)
        CS->>KP: validate_token(JWT, RS256 Public Key)
        KP-->>CS: Payload (user_id, permissions)
    end
    CS-->>C: 200 OK (Данные каталога)
```

### 5.2. Публикация событий (Transactional Outbox)

Гарантирует, что система не окажется в неконсистентном состоянии, если после записи в БД RabbitMQ будет временно недоступен.
```mermaid
%%{init: {'theme': 'dark'}}%%
graph LR
    subgraph "identity-service (API)"
        API["FastAPI App"] -- "1. Single DB Transaction" --> DB[("PostgreSQL")]
        note1["UPDATE users ... <br/> INSERT INTO outbox ..."] -.-> DB
    end
    
    subgraph "identity-service (Worker/Relay)"
        DB -. "2. Polling / NOTIFY" .-> Relay["Outbox Relay"]
    end
    
    subgraph "RabbitMQ"
        Relay -- "3. AMQP Publish" --> EX(("Topic Exchange"))
        EX -- "4. route key: user.created" --> Q1["catalog.users.q"]
        EX -- "4. route key: user.created" --> Q2["support.users.q"]
    end
    
    subgraph "Target Services"
        Q1 -. "5. Consume (Idempotent)" .-> CC["catalog-worker"]
        Q2 -. "5. Consume (Idempotent)" .-> SC["support-worker"]
    end
    
    style API fill:#1e3a8a,stroke:#60a5fa,color:#fff
    style Relay fill:#1e3a8a,stroke:#60a5fa,color:#fff
    style EX fill:#7c2d12,stroke:#fb923c,color:#fff
    style CC fill:#14532d,stroke:#4ade80,color:#fff
```

---
## 6. DevOps и CI/CD

### 6.1. Изолированные миграции БД (Alembic)

Несмотря на Polyrepo, работа с БД прозрачна для разработчика. Каждому сервису выделена своя схема/база и своя таблица `alembic_version`.
```mermaid
%%{init: {'theme': 'dark'}}%%
sequenceDiagram
    autonumber
    actor Dev as Developer
    participant Make as Root Makefile
    participant UV as uv (Virtual Env)
    participant AL as Alembic (Service Context)
    participant DB as PostgreSQL
    
    Dev->>Make: make db-upgrade pkg=identity-service
    
    rect rgb(30, 58, 138)
        Make->>UV: cd services/identity-service && uv sync
        UV-->>Make: Изолированные зависимости готовы
        Make->>AL: uv run alembic upgrade head
    end
    
    rect rgb(20, 83, 45)
        AL->>DB: SELECT version_num FROM alembic_version
        DB-->>AL: Current version: 1234a
        AL->>DB: Применение новых SQL-миграций
        AL->>DB: UPDATE alembic_version SET version_num='5678b'
    end
    
    AL-->>Dev: Миграции успешно применены
```

### 6.2. CI/CD: Матричное тестирование (GitHub Actions)

В монорепозитории тестируется и собирается только то, что изменилось. Матричная сборка запускает проверки параллельно, радикально ускоряя пайплайн.
```mermaid
%%{init: {'theme': 'dark'}}%%
graph LR
    PR(("Push / PR")) --> Checkout["Checkout Code"]
    Checkout --> SetupUV["Setup uv & Cache"]
    
    SetupUV --> Matrix
    
    subgraph "Parallel Matrix Execution (per package)"
        direction TB
        Matrix{"Detect Changes"} 
        Matrix --> Lint["Lint (ruff, mypy)"]
        Matrix --> Test["Test (pytest + coverage)"]
    end
    
    Lint --> Build
    Test --> Build
    
    Build["Build Docker Images"] --> Registry[("Container Registry<br/>(GHCR / DockerHub)")]
    Registry --> Done(("Pipeline Success"))
    
    style PR fill:#1e3a8a,stroke:#60a5fa,color:#fff
    style Done fill:#14532d,stroke:#4ade80,color:#fff
    style Matrix fill:#7c2d12,stroke:#fb923c,color:#fff
    style Registry fill:#0f766e,stroke:#2dd4bf,color:#fff
```

---
## 7. Продвинутые архитектурные паттерны (CQRS, S3, UUID)

В рамках непрерывного развития платформы (согласно **ADR 0023** и **ADR 0024**), архитектура системы включает в себя ряд продвинутых паттернов. Ниже описаны ключевые реализованные концепции.

### 7.1. CQRS и Тонкие контроллеры (ADR 0023)

Для строгого разделения операций чтения и записи во всех микросервисах (`identity`, `catalog`, `support`) внедрен паттерн **CQRS** (Command Query Responsibility Segregation). Следование этому паттерну **жестко контролируется** автоматизированными архитектурными тестами (`check_architecture.py`).

В разделяемой библиотеке `kernel-domain` реализованы базовые абстракции `ICommandHandler` и `IQueryHandler`. Маршрутизаторы (Routers) в `api/v1/` стали максимально тонкими: они лишь валидируют HTTP-запрос через Pydantic и передают DTO в соответствующий Handler. 

Кроме того, интерфейсы-порты репозиториев (например, `UserRepository`, `ProductRepository`, `TicketRepository`) перенесены строго в **Domain-слой**, обеспечивая идеальную инверсию зависимостей (Clean Architecture).
```mermaid
%%{init: {'theme': 'dark'}}%%
graph TD
    subgraph "Presentation Layer (FastAPI)"
        Router["API Router<br/>(Тонкий контроллер)"]
    end
    
    subgraph "Application Layer (CQRS)"
        CH["Command Handler<br/>(Например: CreateProduct)"]
        QH["Query Handler<br/>(Например: GetProduct)"]
    end
    
    subgraph "Domain Layer"
        Port["Repository Port<br/>(IProductRepository)"]
        Entity["Aggregate Root<br/>(Product)"]
    end
    
    subgraph "Infrastructure Layer"
        RepoImpl["SQL Repository<br/>(Implements Port)"]
        DB[("PostgreSQL")]
    end
    
    Router -- "Запись" --> CH
    Router -- "Чтение" --> QH
    
    CH -- "Мутирует" --> Entity
    CH -- "Вызывает интерфейс" --> Port
    QH -- "Читает (Read Model)" --> Port
    
    RepoImpl -. "Реализует" .-> Port
    RepoImpl --> DB
    
    style Router fill:#1e3a8a,stroke:#60a5fa,color:#fff
    style CH fill:#4c1d95,stroke:#a78bfa,color:#fff
    style QH fill:#4c1d95,stroke:#a78bfa,color:#fff
    style Port fill:#14532d,stroke:#4ade80,color:#fff
    style Entity fill:#14532d,stroke:#4ade80,color:#fff
    style RepoImpl fill:#7c2d12,stroke:#fb923c,color:#fff
```

### 7.2. Миграция на UUID (ADR 0024)

Для обеспечения безопасности (защита от перебора/IDOR) и возможности распределенной генерации ключей без блокировок БД, система полностью отказалась от автоинкрементных целочисленных ключей (`int` / `BigInteger`) в пользу **UUIDv4**.

| Модель / Таблица | Старый тип ключа | Текущий тип (Реализовано) | Архитектурное обоснование |
| :--- | :--- | :--- | :--- |
| `Product.id` | `Integer` (Serial) | **`UUID`** | Скрытие объемов продаж бизнеса от конкурентов, предотвращение IDOR. |
| `OutboxMessage.aggregate_id` | `BigInteger` | **`UUID`** | Универсальность полиморфной связи для абсолютно любых доменных сущностей в системе. |
| `User.id` | `UUID` | **`UUID`** | Стандартизация. Внешние ключи между сервисами теперь используют единый формат. |

### 7.3. Медиа-хранилище (MinIO) и Синхронизация Read Models

`catalog-service` полностью реализует хранение изображений товаров через S3-совместимое хранилище (**MinIO**). 
Параллельно RabbitMQ-воркеры обеспечивают консистентность данных: при получении события об удалении/деактивации пользователя из `identity-service`, воркер каталога асинхронно обновляет `owner_read_model`, моментально скрывая товары этого пользователя из поисковой выдачи.
```mermaid
%%{init: {'theme': 'dark'}}%%
sequenceDiagram
    autonumber
    actor C as Client
    participant API as Catalog API (FastAPI)
    participant S3 as MinIO (S3 Bucket)
    participant DB as PostgreSQL
    
    C->>API: PUT /products/{id}/image (File Upload)
    
    rect rgb(30, 58, 138)
        API->>S3: PutObject(bucket="products", key="{uuid}.jpg")
        S3-->>API: 200 OK (ETag, Object URL)
    end
    
    rect rgb(20, 83, 45)
        note over API,DB: CQRS Command Handler
        API->>DB: INSERT/UPDATE ProductImage (S3 URL)
        API->>DB: INSERT OutboxEvent (ProductImageUpdated)
    end
    
    API-->>C: 200 OK (Обновленный профиль товара)
```

### 7.4. Реализация системы тикетов (Support-Service)

В рамках завершения миграции функционала реализован микросервис `support-service`. 
Сервис полностью спроектирован на базе CQRS-конвенции и управляет жизненным циклом обращений пользователей (создание тикетов, отправка сообщений, управление статусами: `OPEN` -> `IN_PROGRESS` -> `RESOLVED`). Все мутации состояния тикетов гарантированно порождают доменные события через инфраструктурный `OutboxMixin`.

---

## 8. Глубокое погружение: Shared Kernel и Хореография микросервисов

### 8.1. Устройство разделяемых библиотек (`libs/`)

В распределенной системе критически важно не дублировать сложный инфраструктурный код, но при этом не создать "распределенный монолит". Пакеты в `libs/` подключаются в изолированные сервисы как локальные зависимости через `uv` (например, `uv add ../../libs/kernel-domain`).

1. **`kernel-domain` (Чистое ядро):** 
   Эта библиотека не имеет сторонних зависимостей. В ней нет ни SQLAlchemy, ни Pydantic, ни FastAPI. Здесь лежат исключительно чистые Python-абстракции, диктующие правила игры:
   - `AggregateRoot`, `Entity`, `ValueObject` (базовые классы DDD).
   - `DomainEvent` (контракт для всех доменных событий).
   - `ICommandHandler` и `IQueryHandler` (интерфейсы CQRS).
2. **`kernel-platform` (Инфраструктурные адаптеры):**
   В отличие от домена, эта библиотека жестко привязана к технологиям. Она инкапсулирует техническую сложность:
   - **Outbox Pattern:** `OutboxMixin` (SQLAlchemy) для автоматической генерации таблиц и сохранения доменных событий внутри транзакций.
   - **RabbitMQ:** Абстракция консьюмера (Consumer) с "подкапотной" реализацией паттернов Dead Letter Queue (DLQ) и Exponential Backoff для ретраев при ошибках сети.
   - **Security:** Валидация JWT-токенов через `PyJWT`, кэширование публичных ключей RSA и проверка пермиссий.
```mermaid
%%{init: {'theme': 'dark'}}%%
graph TD
    subgraph "Слой Микросервиса (напр. identity-service)"
        DomainService["Domain Layer<br/>(Бизнес-логика)"]
        InfraService["Infrastructure Layer<br/>(БД, Сеть)"]
    end
    
    subgraph "Shared Kernel (libs/)"
        KD["kernel-domain<br/>(Pure Python, No Deps)"]
        KP["kernel-platform<br/>(SQLAlchemy, pika, PyJWT)"]
    end
    
    DomainService -- "Наследует абстракции" --> KD
    InfraService -- "Реализует/Использует" --> KP
    KP -- "Зависит от контрактов" --> KD
    
    style DomainService fill:#1e3a8a,stroke:#60a5fa,color:#fff
    style InfraService fill:#7c2d12,stroke:#fb923c,color:#fff
    style KD fill:#14532d,stroke:#4ade80,color:#fff
    style KP fill:#4c1d95,stroke:#a78bfa,color:#fff
```

### 8.2. Межсервисная Хореография (Cross-Service Interaction)

Микросервисы общаются между собой исключительно асинхронно через паттерн **Choreography** (Хореография), реагируя на доменные события друг друга. В системе нет центрального оркестратора — каждый сервис сам знает, что делать при наступлении глобального события.

Рассмотрим самый сложный сквозной поток: **Удаление пользователя**.
```mermaid
%%{init: {'theme': 'dark'}}%%
sequenceDiagram
    autonumber
    actor C as Client (User)
    participant IS as identity-service
    participant MQ as RabbitMQ (Topic Exchange)
    participant CS as catalog-worker
    participant SS as support-worker
    
    C->>IS: DELETE /users/me
    
    rect rgb(30, 58, 138)
        note over IS: Транзакция БД (CQRS Command)
        IS->>IS: Перевод статуса в "deleted"
        IS->>IS: INSERT Outbox(user.deleted)
    end
    
    IS-->>C: 202 Accepted (В обработке)
    
    note over IS,MQ: Outbox Relay асинхронно читает БД
    IS->>MQ: Publish RoutingKey: "user.deleted"
    
    par Fan-out (Параллельная обработка)
        MQ-->>CS: Доставка в catalog.users.q
        MQ-->>SS: Доставка в support.users.q
    end
    
    rect rgb(20, 83, 45)
        note over CS: catalog-service бизнес-логика
        CS->>CS: Обновление owner_read_model
        CS->>CS: Скрытие всех товаров пользователя из выдачи
    end
    
    rect rgb(124, 45, 18)
        note over SS: support-service бизнес-логика
        SS->>SS: Анонимизация открытых тикетов
        SS->>SS: Авто-закрытие тикетов (CLOSED)
    end
```

**Преимущества такого подхода:**
Если `catalog-service` в момент удаления пользователя недоступен (упал или обновляется), событие безопасно останется в очереди RabbitMQ. Как только сервис поднимется, консьюмер прочитает событие и скроет товары. Это обеспечивает **Eventual Consistency** (согласованность в конечном счете) без риска каскадного падения системы.

## Транзакции и Unit of Work (ADR 0034)

### 1. Классовая структура (Dependency Inversion)

```mermaid
%%{init: {'theme': 'dark'}}%%
classDiagram
    direction BT

    class UnitOfWork {
        <<Protocol>>
        +__aenter__() Self
        +__aexit__(exc) None
        +commit() None
        +rollback() None
    }

    class CatalogUnitOfWork {
        <<Protocol>>
        +ProductRepository products
    }
    
    class SqlAlchemyUnitOfWork {
        -AsyncSession _session
        -_committed: bool
        +__aenter__()
        +__aexit__(exc)
        +commit()
        +rollback()
    }

    class SqlCatalogUnitOfWork {
        +SqlProductRepository products
    }

    CatalogUnitOfWork --|> UnitOfWork : extends
    SqlAlchemyUnitOfWork ..|> UnitOfWork : implements
    SqlCatalogUnitOfWork --|> SqlAlchemyUnitOfWork : extends
    SqlCatalogUnitOfWork ..|> CatalogUnitOfWork : implements
```

### 2. Жизненный цикл в Command Handler

```mermaid
%%{init: {'theme': 'dark'}}%%
sequenceDiagram
    participant API as FastAPI Router
    participant Handler as Command Handler
    participant UoW as SqlCatalogUnitOfWork
    participant Repo as ProductRepository
    participant DB as PostgreSQL (AsyncSession)

    API->>Handler: execute(Command)
    
    Handler->>UoW: async with (открытие блока)
    activate UoW
    UoW-->>Handler: __aenter__()
    
    Handler->>Repo: create(product)
    Repo->>DB: session.add(entity)
    
    alt Доменная ошибка (Result.is_err)
        Handler-->>API: return Result.fail(error)
        Note right of UoW: Блок завершается (commit не вызван)
        UoW->>DB: session.rollback() (из __aexit__)
    else Успешное выполнение
        Handler->>UoW: commit()
        UoW->>DB: session.commit()
        Note over DB: Срабатывает OutboxMixin!<br/>События уходят в Outbox таблицу
        Handler-->>API: return Result.ok(ProductView)
    end
    deactivate UoW
```
