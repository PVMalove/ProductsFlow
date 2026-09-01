# 0021. Запись Outbox из доменных событий Product: явный drain в репозитории

`kernel-platform` не содержит `OutboxMixin` — ни identity-service, ни где-либо ещё в кодовой базе строка `outbox_messages` никогда не вставлялась транзакционно вместе с мутацией доменного агрегата (identity вообще не имеет persistence-слоя для `User`, только саму миграцию таблицы `outbox_messages`). `Product` в catalog-service — `Entity[ProductId]` из `kernel-domain` (домен), а `ProductModel` — отдельная SQLAlchemy-модель (инфраструктура); строка outbox должна попасть в ту же транзакцию, что и мутация агрегата, а домен и ORM-слой при этом не должны знать друг о друге напрямую.

**Решение.** `ProductRepository.save()` — единственное место, которое явно видит и доменную сущность, и `AsyncSession`. После маппинга domain → ORM он вызывает `product.pull_events()` и для каждого `DomainEvent` явно добавляет в ту же сессию `OutboxMessage(aggregate_type="Product", aggregate_id=..., event_type=..., payload=..., occurred_at=...)` — один `commit()` фиксирует мутацию агрегата и публикуемые события атомарно. Ничего похожего на ORM-миксин/session-level listener не вводится.

## Considered Options

- **Generic SQLAlchemy session-listener (`before_flush`/`after_flush`), имитирующий `OutboxMixin` из брифа** — сканирует `session.new`/`session.dirty` на предмет доменных событий. Отклонено: требует либо хранить `_domain_events` прямо на ORM-модели (смешивает домен с инфраструктурой), либо тянуть в listener отдельный реестр domain entity ↔ ORM model — сложнее и менее прозрачно, чем один явный вызов в `save()`.
- **`OutboxMixin` в `kernel-platform`** — отклонено дважды: (1) задача прямо запрещает менять что-либо вне `catalog-service`; (2) admission-правило ADR 0013 («минимум два сервиса подтверждённо нуждаются») не выполнено — identity ещё ни разу не писал в outbox из доменной мутации, обобщать не от чего.

## Consequences

- `ProductRepository` явно знает про Outbox — формально шире, чем «репозиторий = только персистентность агрегата», но это осознанный компромисс: только `save()` одновременно видит domain-сущность (события) и `AsyncSession` (транзакцию).
- Если identity-service позже реализует тот же паттерн для `User`, появляется второй подтверждённый потребитель — тогда стоит обобщать в `kernel-platform` (тот же admission-принцип, каким ADR 0019 уже руководствовался для upsert-паттерна read-модели).
