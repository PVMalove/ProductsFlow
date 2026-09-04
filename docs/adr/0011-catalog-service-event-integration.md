# 0011. Catalog: событийная интеграция — consumer, `OwnerReadModel`, собственный Outbox для `Product`

**Статус:** Accepted. Механизм Outbox/RabbitMQ, который catalog только потребляет, полностью описан в [ADR 0010](0010-identity-service-event-integration.md) — здесь не повторяется. Доменные правила видимости товара — [ADR 0008](0008-catalog-service-domain-model.md).

## Потребление: `OwnerReadModel`

Если catalog нужно знать статус пользователя (`is_active`, `role`), он не делает HTTP-запрос в identity на каждый чих — подписывается на `user.*.v1` через очередь `catalog.user-events` ([ADR 0010](0010-identity-service-event-integration.md)) и строит локальную проекцию `OwnerReadModel`.

**Версионирование против гонки доставки.** `aio-pika` доставляет сообщения отдельными asyncio-задачами — порядок обработки внутри одного консьюмера не гарантирован даже при одном consumer'е. `OwnerReadModel` хранит `last_applied_outbox_id` и применяет входящее состояние атомарным upsert с условием, не read-затем-write в коде приложения:

```sql
INSERT INTO owner_read_model (user_id, role, is_active, last_applied_outbox_id)
VALUES (:user_id, :role, :is_active, :incoming_id)
ON CONFLICT (user_id) DO UPDATE
SET role = EXCLUDED.role, is_active = EXCLUDED.is_active,
    last_applied_outbox_id = EXCLUDED.last_applied_outbox_id
WHERE owner_read_model.last_applied_outbox_id < EXCLUDED.last_applied_outbox_id;
```

`message.message_id` уже равен `outbox_messages.id` — источник версии берётся из метаданных доставки AMQP бесплатно, без изменения схемы payload. Идемпотентность (`processed_messages`, защита от повторной обработки **того же** сообщения) и версионирование (`last_applied_outbox_id <`, защита от применения **другого**, но более старого сообщения) — два взаимодополняющих guard'а в одной транзакции консьюмера.

## Синхронные точки поверх eventual consistency

Eventual consistency — правило по умолчанию, но с двумя узкими исключениями:

- **Промах read-модели (холодный старт).** Токен валиден, строки `OwnerReadModel` ещё нет — catalog делает один синхронный вызов `IdentityClient.fetch_current_user()` (`GET /api/v1/users/me`, JWKS-верифицированный bearer, [ADR 0005](0005-security-auth-actor-contract.md)) и пишет строку с `last_applied_outbox_id = 0` — заведомо проигрывающий сентинел: любое настоящее событие (`id ≥ 1`) гарантированно его перезаписывает.
- **Админская ветка.** Синхронная сверка выполняется только когда доступ даётся ролью `admin`, а не владением — владение (`product.user_id == current_user.id`) не протухает и синхронной проверки не требует. Устаревший `role=ADMIN` у уже понижённого пользователя — окно эскалации привилегий, а не просто устаревшей видимости.
- **Недоступность identity — fail closed.** Админские действия отвечают `503`; обычные пользователи не затронуты.

**Асимметрия деактивации.** Для админов деактивация применяется мгновенно; для обычных пользователей — за секунды, равные задержке доставки события. Другое поведение для support — [ADR 0012](0012-support-service-event-integration.md): там нет ни одной из этих двух синхронных точек.

## Собственный Outbox для `Product`

Catalog — не только потребитель, но и второй (после identity) producer transactional outbox, для агрегата `Product`. `ProductRepository.save()`/`delete()` вызывает общий `drain_events_to_outbox(self.session, product)` ([ADR 0006](0006-service-internal-architecture-baseline.md), [ADR 0010](0010-identity-service-event-integration.md)) в той же транзакции, что и мутация агрегата. Пять подклассов `ProductEvent` реализуют контракт `DomainEvent`: общий предок задаёт `aggregate_type = "Product"` и `aggregate_id()`/базовый `to_payload()` (`{"product_id": ...}`), `ProductCreated` расширяет `to_payload()` через `super()`, остальные четыре только объявляют свой `event_type`.

## Considered Options

- **Синхронная сверка `is_active`/`role` на каждой мутации** — отклонено: возвращает вызов к identity на каждый запрос, ради устранения которого read-модель и вводилась.
- **Отказ `403` при промахе read-модели вместо синхронного добора** — отклонено: первый запрос каждого нового пользователя мог бы отказать сразу после регистрации.
- **Fail open при недоступности identity** — отклонено: открывает окно эскалации привилегий ровно тогда, когда его труднее всего заметить.

## Consequences

- Catalog — единственный сервис, одновременно являющийся полноценным consumer'ом (`OwnerReadModel`) и producer'ом (`Product`-события).
- Сбой identity парализует админскую работу в catalog (`503`), но не чтение публичной витрины и не действия обычных пользователей над своими товарами.
- `last_applied_outbox_id = 0`, не подтверждённый ни одним реальным событием, навсегда остаётся легитимно перезаписываемым — не баг, а следствие того, что `0` спроектирован как всегда проигрывающая версия.
