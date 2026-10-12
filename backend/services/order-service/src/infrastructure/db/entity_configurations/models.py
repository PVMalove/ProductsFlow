import uuid
from datetime import datetime
from typing import Any

from kernel_platform.outbox.models import Base
from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

# Общий `kernel_platform.outbox.models.Base` (issue #376, архитектурный бриф
# D6) — разворот решения #369/#372 (собственный `Base`), по прецеденту
# payment-service #371: order-service теперь эмитит доменное событие
# `order.completed.v1` через `drain_events_to_outbox` в общий
# `outbox_messages`. Импорт этого `Base` регистрирует `OutboxMessage` и
# `InboxMessage` на одном `Base.metadata` (`inbox_messages` не используется,
# R5). Исходящие Saga-команды остаются в собственной `reservation_outbox`:
# её UUID `id` напрямую годится как `Command.command_id` (находка 5,
# `OutboxMessage`'s BigInt PK несовместим).


class CartModel(Base):
    """Один `Cart` на пользователя — `UNIQUE(user_id)` (D3)."""

    __tablename__ = "carts"
    __table_args__ = (UniqueConstraint("user_id", name="uq_carts_user_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class CartLineModel(Base):
    """`ON DELETE CASCADE` — удаление корзины удаляет её строки.
    `UNIQUE(cart_id, product_id)` — инвариант «одна строка на товар в корзине»
    (D4); `CHECK(quantity > 0)` — Always-Valid на уровне БД, продублировано
    доменной валидацией."""

    __tablename__ = "cart_lines"
    __table_args__ = (
        UniqueConstraint(
            "cart_id", "product_id", name="uq_cart_lines_cart_id_product_id"
        ),
        CheckConstraint("quantity > 0", name="ck_cart_lines_quantity_positive"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    cart_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("carts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    product_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    added_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    # issue #372, D3/D7: `locked_by_order_id` — Checkout Selection freeze;
    # `unavailable_reason` — заполняется только на терминале частичного
    # резерва. Оба nullable/additive — существующие строки #369 не затронуты.
    locked_by_order_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    unavailable_reason: Mapped[str | None] = mapped_column(Text, nullable=True)


class OrderModel(Base):
    """Агрегат `Order` (issue #372, D4). `status` — внешний ADR 0016:7
    набор; `saga_step` — внутренний, не раскрывается клиенту."""

    __tablename__ = "orders"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(Text, nullable=False)
    saga_step: Mapped[str] = mapped_column(Text, nullable=False)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    # issue #375, D1: id авторизации payment-service после
    # `payment.authorized.v1`; `NULL` до успешной авторизации.
    payment_authorization_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )


class OrderLineModel(Base):
    """`ON DELETE CASCADE` — удаление заказа удаляет его строки. Набор строк
    только сокращается после создания (D7), никогда не растёт."""

    __tablename__ = "order_lines"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("orders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    product_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_price_kopecks: Mapped[int] = mapped_column(Integer, nullable=False)


class OrderSagaTransitionModel(Base):
    """Неизменяемая техническая история Saga (issue #376, D5; ADR 0016:15):
    одна строка на каждое изменение `(saga_step, status)` Order, пишется
    централизованно в `OrderRepository.save`. Append-only — код не обновляет
    и не удаляет строки; порядок задаёт BigInt sequence `id`. Корреляция —
    `order_id` (каждое сообщение Saga несёт `correlation_id = str(order_id)`);
    causation/trace-колонки — забота #378."""

    __tablename__ = "order_saga_transitions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("orders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    saga_step: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class IdempotencyKeyModel(Base):
    """Idempotency-Key запись (issue #372, D2) — составной PK
    `(user_id, key)`, буквальная HTTP Idempotency-Key семантика."""

    __tablename__ = "idempotency_keys"

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    key: Mapped[str] = mapped_column(Text, primary_key=True)
    request_fingerprint: Mapped[str] = mapped_column(Text, nullable=False)
    order_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ReservationOutboxModel(Base):
    """Исходящий command-intent Saga (issue #372, D6) — собственная таблица
    order-service, НЕ `kernel_platform.OutboxMessage` (находка 5: `id` здесь
    напрямую годится как `Command.command_id`, UUID, не BigInt). Дренаж —
    `ReservationOutboxPublisher`, тот же `FOR UPDATE SKIP LOCKED`/backoff
    идиом, что generic `OutboxPublisher`.

    issue #375, D3: `command_type` — таблица несёт не только
    `inventory.reserve.v1`, но и `payment.authorize.v1`/`inventory.release.v1`.
    Имя `reservation_outbox` — известный naming debt (R5), переименование —
    отдельный рефакторинг."""

    __tablename__ = "reservation_outbox"
    __table_args__ = (
        Index(
            "ix_reservation_outbox_unpublished",
            "id",
            postgresql_where=text("published_at IS NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    order_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    command_type: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    next_attempt_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class ProcessedMessageModel(Base):
    """Inbox-гейт order-worker'а (issue #372, D7 — зеркалит inventory-worker's
    `ProcessedMessage`, issue #367) для входящих событий: generic
    `inbox_messages` ключуется UUID `command_id` команд и сюда не подходит
    (см. модульный комментарий).

    issue #375, D4: PK `(source, message_id)` — `message_id` это BigInt
    sequence outbox'а КАЖДОГО producer'а (inventory, payment), обе стартуют с
    1; PK только по `message_id` молча пропустил бы событие payment с id уже
    обработанного события inventory."""

    __tablename__ = "processed_messages"

    source: Mapped[str] = mapped_column(Text, primary_key=True)
    message_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    processed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
