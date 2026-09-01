# 0024. Все ID агрегатов — GUID

`identity.UserId` — GUID с самого начала (ADR TD-01 Фаза 1, `identity/domain/user_id.py`). `catalog.ProductId` (issue #148/#149) — `int` (Postgres `BigInteger Identity`, миграция `7e6095c037fb`): не архитектурный выбор, а следствие узкого мандата той задачи — «менять что-либо вне catalog-service запрещено» (ADR 0021, отклонённый вариант «`OutboxMixin` в `kernel-platform`»), а `kernel_platform.OutboxMessage.aggregate_id` уже был типизирован `BigInteger` на момент, когда `ProductId` понадобился. Результат — два агрегата с разной формой первичного ключа без единой причины, кроме порядка, в котором писался код.

**Решение.** Единая конвенция для всех сервисов: PK агрегата — GUID (`uuid.UUID`, Postgres `UUID`), без исключений. Отсюда:

- `catalog.ProductId.value` меняется с `int` на `uuid.UUID` (по образцу `identity.UserId`); `products.id` — `UUID`, не автоинкремент.
- `kernel_platform.OutboxMessage.aggregate_id` меняется с `BigInteger` на `UUID` — это общая инфраструктура, которую использует catalog уже сейчас и на которую рассчитан identity, когда там появится persistence-слой для `User` (тот же `UserId`, уже GUID); привести её к единому виду сейчас дешевле, чем потом мигрировать под нагрузкой в проде.
- Причина выбора GUID, а не int: агрегаты создаются в разных сервисах независимо друг от друга (нет единого источника последовательности), а PK не должен течь между сервисами как угадываемый инкремент (эксплуатационная гигиена микросервисной границы) — то же обоснование, по которому `UserId` изначально стал GUID.

## Considered Options

- **Оставить `ProductId` как есть (`int`)** — отклонено: закрепляет расхождение, возникшее по случайной причине (порядок реализации, а не осознанный выбор), и не даёт единообразия, на которое рассчитывает разбираемый в issue #158/#160 CQRS/DIP-рефакторинг (Command/Query/Repository-порты не должны решать по сервису, какой тип у ID).
- **Тип-агностичный `aggregate_id` в `kernel_platform`** (например, `String`, вмещающий и `int`, и `uuid`) — отклонено: усложняет схему и сериализацию ради гипотетической будущей потребности в `int`-агрегате, которой нет ни у одного текущего или планируемого сервиса.
- **GUID только для новых агрегатов, `ProductId` не трогать** — отклонено пользователем явно: цель — единообразие по всей кодовой базе, не только вперёд.

## Consequences

- Ретрофит `catalog.ProductId`: `catalog/domain/product_id.py` (тип, докстринг), `catalog/infrastructure/db/models.py` (`ProductModel.id`), новая Alembic-ревизия для `products.id` (нельзя редактировать уже смёрженную `7e6095c037fb` — добавляется новая), `catalog/infrastructure/db/product_repository.py`, `catalog/infrastructure/db/pagination.py` (курсор `(created_at, id)` — `id` меняет тип, сама схема курсора не меняется), `catalog/api/schemas.py`/`products.py`, `catalog/infrastructure/db/audit.py`, все тесты (~30 в `test_products_api.py` + смежные), уже открытый PR #155 — эта ADR не ретрофитит его сама (см. issue).
- Ретрофит `kernel_platform.OutboxMessage.aggregate_id`: `backend/libs/kernel-platform/src/kernel_platform/outbox/models.py`, Alembic-ревизия identity-service для `outbox_messages` (`aggregate_id` создавалась `BigInteger` там же, ADR 0014/0017), `OutboxPublisher`/связанные тесты, если они завязаны на тип колонки.
- Формулировки, ссылающиеся на прежнее состояние, помечаются устаревшими: докстринг `product_id.py` («не GUID, в отличие от `identity.UserId`»), ADR 0021 §Consequences (упоминание `BigInteger` как данности) — не переписываются задним числом, актуальность передаётся через эту ADR.
- Ничего не меняется для `identity.UserId` — уже GUID, эта ADR лишь формализует то, что там уже было верно с самого начала.
