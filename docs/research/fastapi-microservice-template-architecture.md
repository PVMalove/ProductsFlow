# Архитектурный референс: `fastapi-microservice-template`

Дата исследования: 2026-09-01\
Референс: [`onlythompson/fastapi-microservice-template`](https://github.com/onlythompson/fastapi-microservice-template), зафиксированный commit [`7d1908b`](https://github.com/onlythompson/fastapi-microservice-template/tree/7d1908bdfea69adb46213cbee85c718fd63a28e9)

## Цель и границы

Эта заметка фиксирует только практики, прямо заявленные или созданные в исходных документах и генераторе структуры референса. Это не рекомендация копировать шаблон целиком: его публичный репозиторий — каркас и документация, а не готовая реализация сервиса. Следовательно, каждое решение нужно проверять на соответствие существующим bounded contexts, нагрузке и эксплуатационным требованиям ProductsFlow AI.

## Подтверждённые практики

### 1. Явная слоистая граница и направление зависимостей

Референс задаёт четыре основных слоя: `domain`, `application`, `infrastructure` и `presentation`. В его архитектурном документе сформулировано правило: зависимости направлены внутрь, а внутренние слои не знают о внешних. Там же инфраструктура определена как место реализации абстракций и внешних интеграций. [Architecture: principles and layers](https://github.com/onlythompson/fastapi-microservice-template/blob/7d1908bdfea69adb46213cbee85c718fd63a28e9/docs/architecture.md)

Практический вывод для ADR/issue: каждое архитектурное требование должно называть владельца контракта, реализацию и composition root. Формулировки вида «использовать репозиторий» недостаточны, если не установлено, какой слой владеет портом, а какой — адаптером.

### 2. Структура создаётся повторяемо, а не описывается только на словах

Генератор создаёт изолированные каталоги для application (`interfaces`, `services`, `use_cases`), domain (`entities`, `value_objects`, `events`), infrastructure (`database`, `repositories`, `messaging`, `cache`), presentation, а также отдельные наборы unit/integration/e2e-тестов. [Generator source](https://github.com/onlythompson/fastapi-microservice-template/blob/7d1908bdfea69adb46213cbee85c718fd63a28e9/scripts/generate_project_structure.py)

Практический вывод: ADR должен фиксировать минимальную целевую структуру и правила импорта, а issue — перечислять конкретные перемещения/новые модули и проверку, что новые зависимости их соблюдают. Не следует создавать пустые «на всякий случай» каталоги или обобщения, если у изменения нет конкретного потребителя.

### 3. События и CQRS применяются избирательно

В архитектурном описании events отнесены к domain-слою, а CQRS — к application-слою. ADR референса не вводит CQRS глобально: он предписывает начать с нагруженного/сложного домена `Order`, разделить command и query стороны, обновлять денормализованную read-модель обработчиками событий и отдельно признаёт цену решения — сложность и eventual consistency. [Architecture: patterns](https://github.com/onlythompson/fastapi-microservice-template/blob/7d1908bdfea69adb46213cbee85c718fd63a28e9/docs/architecture.md) [ADR-0001: scoped CQRS decision](https://github.com/onlythompson/fastapi-microservice-template/blob/7d1908bdfea69adb46213cbee85c718fd63a28e9/docs/adr/0001-use-cqrs-pattern.md)

Практический вывод: для каждой ADR о CQRS/outbox/read model нужны: границы применения (какой контекст и сценарии), источник истины write-side, способ доставки/обработки события, ожидаемая консистентность и измеримый критерий пересмотра. CQRS не должен быть обязательным для обычных CRUD-путей лишь из-за наличия шаблона.

### 4. Инфраструктурные зависимости — внешние детали с явными операционными целями

Референс связывает PostgreSQL с персистентностью, Redis — с кэшем и распределёнными блокировками, Kafka — с асинхронной коммуникацией; Docker Compose предназначен для локального запуска этих зависимостей вместе с приложением. [Architecture: external dependencies and deployment](https://github.com/onlythompson/fastapi-microservice-template/blob/7d1908bdfea69adb46213cbee85c718fd63a28e9/docs/architecture.md) [Compose definition](https://github.com/onlythompson/fastapi-microservice-template/blob/7d1908bdfea69adb46213cbee85c718fd63a28e9/docker-compose.yaml)

Практический вывод: ADR, выбирающая брокер, кэш или базу, должна фиксировать не только технологию, но и ответственность сервиса, контракт обмена, локальную/тестовую топологию, обработку ошибок и наблюдаемость. Технология не заменяет эти решения.

### 5. Эксплуатационные и тестовые границы входят в архитектуру

Шаблон документирует изолированные unit, integration и e2e тесты; также предусматривает `core` для кросс-срезных задач, включая конфигурацию, логирование, telemetry, health и security. Его описание масштабирования предполагает stateless-приложение, распределённый кэш, асинхронный обмен и read replicas, но это именно заявленная целевая архитектура, а не доказательство готовности конкретного кода. [Architecture: structure and scalability](https://github.com/onlythompson/fastapi-microservice-template/blob/7d1908bdfea69adb46213cbee85c718fd63a28e9/docs/architecture.md) [Testing strategy](https://github.com/onlythompson/fastapi-microservice-template/blob/7d1908bdfea69adb46213cbee85c718fd63a28e9/docs/testing.md)

Практический вывод: архитектурные issues должны содержать проверяемый уровень теста и операционный контракт (например, health/log/trace/event retry), а не ограничиваться рефакторингом расположения файлов.

### 6. ADR содержит решение, цену и точку пересмотра

README референса выделяет `docs/adr/` для значимых решений. Его ADR о CQRS содержит статус, контекст, решение, положительные и отрицательные последствия, детали внедрения, измеримые метрики успеха и дату review. [README: ADR index](https://github.com/onlythompson/fastapi-microservice-template/blob/7d1908bdfea69adb46213cbee85c718fd63a28e9/README.md) [ADR-0001](https://github.com/onlythompson/fastapi-microservice-template/blob/7d1908bdfea69adb46213cbee85c718fd63a28e9/docs/adr/0001-use-cqrs-pattern.md)

Практический вывод: исправляемая ADR должна быть decision record, а не проектной заметкой: указать статус, проблему и scope, выбранный вариант, альтернативы, последствия/риски, миграционные шаги и условия пересмотра. Связанный issue превращает это в проверяемую работу с конкретными affected modules и acceptance criteria.

## Что не переносить без отдельного обоснования

- В референсе интерфейсы репозиториев расположены в `application/interfaces`, а не в `domain`; это альтернативный выбор владельца порта, а не универсальное правило. В ProductsFlow AI он должен быть согласован с собственным DDD-словарём и уже принятыми ADR, а не принят по аналогии. [Architecture: application and infrastructure layers](https://github.com/onlythompson/fastapi-microservice-template/blob/7d1908bdfea69adb46213cbee85c718fd63a28e9/docs/architecture.md)
- Redis, Kafka, Kubernetes, Event Sourcing, read replicas и CQRS перечислены как возможности/целевые паттерны. Сам README называет их feature-ами, но не показывает production-реализацию в репозитории. Их внедрение требует отдельного ADR с проблемой, альтернативами и последствиями. [README: features and project structure](https://github.com/onlythompson/fastapi-microservice-template/blob/7d1908bdfea69adb46213cbee85c718fd63a28e9/README.md)
- В самом генераторе создание `docs/` и `docs/adr/` закомментировано, хотя README и архитектурный документ их описывают. Это дополнительный сигнал не трактовать шаблон как нормативный исполнимый стандарт без сверки документации и кода. [Generator source](https://github.com/onlythompson/fastapi-microservice-template/blob/7d1908bdfea69adb46213cbee85c718fd63a28e9/scripts/generate_project_structure.py)

## Использование при правке ADR и issues

Использовать референс как чек-лист качества формулировки, а не как схему миграции:

1. Привязать решение к одному bounded context и одному наблюдаемому симптому/цели.
2. Явно обозначить слой-владельца контракта, адаптер и место сборки зависимостей.
3. Для асинхронного или CQRS-потока описать источник истины, событие, read-side, согласованность и отказные сценарии.
4. Задать acceptance criteria: изменённые границы импортов, требуемые тесты и операционные сигналы.
5. Не вводить инфраструктурную технологию или новый общий модуль без подтверждённого сценария и альтернатив.
