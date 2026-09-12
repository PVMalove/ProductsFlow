import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# Собственный `Base`, НЕ общий `kernel_platform.outbox.models.Base` (issue #369,
# архитектурный бриф D1): order-service не публикует и не потребляет
# сообщения в этом тикете, поэтому его схема не должна тянуть за собой
# `outbox_messages`/`inbox_messages` (тот же выбор, что payment-service уже
# сделал для #368).


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
