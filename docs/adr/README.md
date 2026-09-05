# ADR: индекс

Актуальная база архитектурных решений — 13 документов, нумерация с 0001. Прежняя, более многочисленная и местами противоречивая база (включая её собственную нумерацию) полностью заменена этим набором; при построении каждого документа противоречия между историческими решениями разрешались по правилу «новее (по дате или большему номеру исходного решения) побеждает» — устаревшая версия решения в новую базу не переносится.

## 1. Общая архитектура платформы

| ADR | Название |
|---|---|
| [0001](0001-platform-topology-and-bounded-contexts.md) | Топология платформы, точки входа и границы контекстов |

## 2. Глобальные архитектурные решения и контракты

| ADR | Название |
|---|---|
| [0002](0002-bff-response-envelope.md) | BFF API: единый конверт ответа |
| [0003](0003-centralized-error-handling.md) | Централизованная обработка ошибок |
| [0004](0004-api-gateway-and-routing.md) | Роутинг: единая версия API и E2E-only Gateway |
| [0005](0005-security-auth-actor-contract.md) | Безопасность: RS256/JWKS, единый контракт `Actor`, RBAC |

## 3. Внутрисервисная бизнес-логика

| ADR | Название |
|---|---|
| [0006](0006-service-internal-architecture-baseline.md) | Канон внутренней архитектуры сервиса: Hexagonal, Always-Valid Domain, CQRS, Unit of Work |
| [0007](0007-identity-service-domain-model.md) | Identity: доменная модель и бизнес-правила |
| [0008](0008-catalog-service-domain-model.md) | Catalog: доменная модель и бизнес-правила |
| [0009](0009-support-service-domain-model.md) | Support: доменная модель и бизнес-правила |

## 4. Межсервисное взаимодействие

| ADR | Название |
|---|---|
| [0010](0010-identity-service-event-integration.md) | Identity: событийная интеграция — единственный producer, Outbox, топология RabbitMQ |
| [0011](0011-catalog-service-event-integration.md) | Catalog: событийная интеграция — consumer, `OwnerReadModel`, собственный Outbox для `Product` |
| [0012](0012-support-service-event-integration.md) | Support: событийная интеграция — consumer, `user_projection`, deny-by-default, tombstone-обработка |

## 5. Стратегия тестирования

| ADR | Название |
|---|---|
| [0013](0013-testing-strategy.md) | Стратегия тестирования: пирамида, E2E через Gateway, изоляция окружения и данных |

## 6. Контракт ошибок

| ADR | Название |
|---|---|
| [0014](0014-error-collections-and-bff-validation-details.md) | Коллекции доменных ошибок и детали ошибок в BFF |
