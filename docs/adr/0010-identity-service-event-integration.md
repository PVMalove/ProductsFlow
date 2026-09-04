# 0010. Identity: событийная интеграция — единственный producer, Outbox, топология RabbitMQ

**Статус:** Accepted. Доменная часть `User`/Tombstone — [ADR 0007](0007-identity-service-domain-model.md). Общий канон Unit of Work и `drain_events_to_outbox` как explicit-вызова — [ADR 0006](0006-service-internal-architecture-baseline.md).

`identity-service` — единственный писатель `outbox_messages` и единственный producer событий в системе (catalog и support — consumer'ы; catalog дополнительно имеет собственный producer для `Product`, см. [ADR 0011](0011-catalog-service-event-integration.md)).

## Событийный каталог

Routing key = `user.<событие>.v1`, exchange `productsflow.events` (topic, durable, объявляется identity на старте — единственный продюсер):

| Событие | Когда |
|---|---|
| `user.registered.v1` | Успешная саморегистрация |
| `user.activated.v1` / `user.deactivated.v1` | Переключение `is_active` (владельцем/админом) |
| `user.role_changed.v1` | Смена `role` (в т. ч. промоушен в admin при сидировании, [ADR 0001](0001-platform-topology-and-bounded-contexts.md)) |
| `user.deleted.v1` | Самостоятельное удаление — `User` заменяется Tombstone ([ADR 0007](0007-identity-service-domain-model.md)) |

**Версионирование (`.v1` → `.v2`).** Новая версия схемы события — новый routing key, не новый exchange; биндинг потребителя расширяется с `user.*.v1` до `user.*.*` (или второй биндинг) при появлении `v2`. Спекулятивная инфраструктура под это не заводится.

## Transactional Outbox: механизм пробуждения и гарантии

Приемлемое окно рассинхронизации между записью события и его применением в read-модели потребителя — секунды.

- **Пробуждение — гибрид.** `LISTEN/NOTIFY` даёт почти мгновенную реакцию; фоновый polling раз в 5 секунд — страховка от потери fire-and-forget `NOTIFY`, если воркер в момент отправки не слушает (рестарт, разрыв соединения). Запрос — `WHERE published_at IS NULL AND next_attempt_at <= now()`.
- **Блокировка строк — `SELECT ... FOR UPDATE SKIP LOCKED`.** Один экземпляр воркера на сервис сегодня; `SKIP LOCKED` оставляет дверь к горизонтальному масштабированию воркера открытой без переделки.
- **`attempts` — только backoff, без give-up.** Publisher никогда не сдаётся: отказ от повторной отправки после исчерпания счётчика ломает гарантию At-Least-Once. `next_attempt_at` — производная колонка, чтобы poll-запрос не перебирал строки, которым рано повторяться.
- **`published_at` подтверждается только `Basic.Ack` брокера.** `ReturnedMessage` (сообщение не доставлено ни одной очереди) — структурная ошибка топологии, не транзиентный сбой: не ретраится, логируется как аномалия.

**Схема `outbox_messages`:** `id` (`bigserial` PK — источник тотального порядка доставки и порядка агрегата), `aggregate_type`, `aggregate_id` (индексированный фильтр порядка по агрегату), `event_type`, `payload` (`jsonb`), `occurred_at`, `published_at` (nullable, частичный индекс `WHERE published_at IS NULL`), `attempts` (default 0), `next_attempt_at` (nullable), `trace_context` (задел для будущей OTEL-инъекции `traceparent`).

**Порядок для read-моделей — побочный продукт `id`.** identity — единственный писатель, воркер — один экземпляр, поэтому порядок вставки совпадает с порядком `id`. Фильтр по `aggregate_type`+`aggregate_id` даёт read-моделям потребителей тотальный порядок событий одного пользователя бесплатно, без отдельного счётчика версии на самом агрегате `User`. Гарантия опирается на условие «один воркер, один писатель» — при горизонтальном масштабировании воркера предположение придётся пересмотреть явно.

## Generic DomainEvent → Outbox drain (kernel-platform)

`kernel_domain.DomainEvent` даёт контракт (`aggregate_id()`, `to_payload()`, [ADR 0006](0006-service-internal-architecture-baseline.md)); `kernel_platform.outbox.drain.drain_events_to_outbox(session, entity)` — generic-операция, вызывающая `entity.pull_events()` и добавляющая в переданную сессию по одному `OutboxMessage` на событие (без коммита — транзакция за вызывающим репозиторием). Функция ничего не знает о конкретных агрегатах, полностью управляется контрактом `DomainEvent`. Вызывается явно из repository-метода в точке мутации (не автоматически из `session.new`/`session.dirty`) — тот же код обслуживает и `identity`'s `User`, и `catalog`'s `Product`.

## RabbitMQ-топология, которую identity объявляет

- **Exchange:** `productsflow.events` (topic, durable) — объявляется identity на старте.
- **Основные очереди потребителей** — `catalog.user-events`, `support.user-events`: quorum (только они поддерживают `x-delivery-limit`), wildcard-биндинг `user.*.v1`. Одна очередь на сервис, не на тип события — все типы событий одного пользователя должны применяться к одной read-модели в предсказуемом порядке.
- **DLQ.** Общий DLX `productsflow.dlx` (direct), отдельная очередь на сервис (`catalog.user-events.dlq`, `support.user-events.dlq`).
- **Retry-лестница — три TTL-ступени на сервис (5с/30с/2мин), не настоящий exponential backoff.** Механизм — управляется потребителем (чтение `x-death`, публикация в нужную ступень через default exchange, `ack` исходной доставки), не declarative DLX-цепочкой. После трёх попыток — `reject(requeue=False)`, срабатывает статический DLX очереди. `x-delivery-limit` (RabbitMQ-дефолт 20) — страховка от бага в подсчёте ступеней, не основной механизм.
- **`message_id` = `outbox_messages.id`** — идемпотентность потребителя по `processed_messages` без отдельного механизма.
- **Объявление — идемпотентно на старте**, без отдельного deploy-шага: `declare_exchange`/`declare_queue` в `aio-pika` безопасны к повторным параллельным вызовам с теми же параметрами.

## Considered Options

- **Только polling, без `LISTEN/NOTIFY`** — отклонено: даже щедрый интервал ближе к верхней границе допустимого окна, чем гибрид.
- **Только `LISTEN/NOTIFY`, без polling-страховки** — отклонено: пропущенное уведомление зависает без срока при рестарте воркера, неизбежном при каждом деплое.
- **Полноценный exponential backoff (N растущих retry-очередей)** — отклонено: три TTL-ступени дают то же качественное поведение при кратно меньшей сложности для ожидаемо транзиентных сбоев.
- **Общая DLQ на оба сервиса** — отклонено: смешивает отравленные сообщения двух сервисов, усложняя разбор.
- **Очередь на тип события вместо очереди на сервис** — отклонено: разнесло бы события одного пользователя по независимым консьюмерам без гарантии взаимного порядка.

## Consequences

- Любой будущий producer (например, support для `Ticket`) подключается к транзакционному outbox, только реализовав `DomainEvent`-контракт и вызвав `drain_events_to_outbox` — без нового кода в `kernel-platform`.
- Сбой identity не блокирует чтение catalog/support своих read-моделей, но блокирует синхронные точки сверки catalog ([ADR 0011](0011-catalog-service-event-integration.md)) и появление новых событий в системе.
