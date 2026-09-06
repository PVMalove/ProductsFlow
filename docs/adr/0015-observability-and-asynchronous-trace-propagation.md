# 0015. Наблюдаемость: локальный стек и асинхронная W3C-трассировка

**Статус:** Accepted.

Локальный Prometheus/Loki/Tempo/Grafana-стек является opt-in Compose overlay и использует уже развёрнутый MinIO как S3-совместимое хранилище Loki и Tempo. Monitoring overlay включает JSON-журнал приложения, чтобы Loki мог извлечь `trace_id` и Grafana могла открыть связанный trace в Tempo. Для сохранения одного распределённого трейса через Transactional Outbox W3C `traceparent` и `tracestate` фиксируются в строке Outbox в транзакции, породившей событие; publisher передаёт их RabbitMQ, а общий consumer извлекает их перед спаном `consume_message`. Carrier хранится в существующей `trace_context` как JSON с обратносуместимым чтением прежнего строкового `traceparent`. Это намеренно не связывает сообщение с текущим контекстом отдельного publisher-процесса: тот обычно уже не является потомком исходного HTTP-запроса.

## Consequences

- OpenTelemetry SDK запускается в каждом API- и worker-процессе с его точным именем сервиса.
- Экспорт трейсов best-effort: недоступность Tempo и переполнение ограниченной очереди BatchSpanProcessor не блокируют приложение.
- Точки RabbitMQ-потребления инструментируются в `kernel_platform.consumer`; PostgreSQL `LISTEN/NOTIFY` остаётся только механизмом пробуждения Outbox publisher.
- Prometheus собирает только HTTP-метрики API; `/metrics` не проходит через Gateway и не инструментируется, а набор меток не включает пользовательские и высококардинальные значения.
- Loki и Tempo получают отдельные buckets в уже существующем MinIO; одноразовый `monitoring-minio-init` идемпотентно создаёт их до старта хранилищ, поэтому их создание не относится к bootstrap Catalog.
- Наружу опубликован только Grafana `localhost:3300` (внутри контейнера — `3000`); Tempo OTLP, Loki, Prometheus, MinIO и вспомогательный Redis остаются во внутренней Docker-сети. Grafana использует локальные `admin`/`admin`, переопределяемые переменными окружения.
- Tempo кэширует результаты поиска трейсов (роль `frontend-search`) в отдельном Redis-инстансе overlay — эфемерные данные, без persistence; недоступность кэша не блокирует поиск, он просто идёт мимо в S3.
- Внутренние gRPC/HTTP-лимиты Loki (max message size, concurrent streams, таймауты) подняты сверх дефолтов одного сервиса — под объём логов всего backend-стека сразу, чтобы широкий Explore-запрос из Grafana не упирался в ResourceExhausted на внутреннем querier ↔ query-frontend вызове.
- Стек запускается явной командой `docker compose` с monitoring overlay; новый Make target не вводится.
