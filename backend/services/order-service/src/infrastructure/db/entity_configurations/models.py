import uuid
from datetime import datetime
from typing import Any

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
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# Собственный `Base`, НЕ общий `kernel_platform.outbox.models.Base` (issue #369,
# архитектурный бриф D1). issue #372 добавляет order-service собственные
# `reservation_outbox`/`processed_messages` (D6/D7/D8) — но НЕ переиспользует
# generic `kernel_platform.outbox.models.Base` (`OutboxMessage`/`InboxMessage`,
# BigInt PK): типовой конфликт с UUID `command_id` (находка 5), и order не
# эмитит доменные события через `drain_events_to_outbox` — только исходящие
# Saga-команды через свою собственную таблицу.


class Base(DeclarativeBase):
    pass


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
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    saga_step: Mapped[str] = mapped_column(Text, nullable=False)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
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
    """Исходящий command-intent для `inventory.reserve.v1` (issue #372, D6) —
    собственная таблица order-service, НЕ `kernel_platform.OutboxMessage`
    (находка 5: `id` здесь напрямую годится как `Command.command_id`, UUID,
    не BigInt). Дренаж — `ReservationOutboxPublisher`, тот же
    `FOR UPDATE SKIP LOCKED`/backoff идиом, что generic `OutboxPublisher`."""

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
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    next_attempt_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class ProcessedMessageModel(Base):
    """Inbox-гейт order-worker'а для `inventory.reserved.v1` (issue #372,
    D7 — зеркалит inventory-worker's `ProcessedMessage`, issue #367). Свой
    `Base`, не `kernel_platform.outbox.models.Base`: order-service не заводит
    generic `outbox_messages`/`inbox_messages` таблицы (см. модульный
    докстринг)."""

    __tablename__ = "processed_messages"

    message_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    processed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
