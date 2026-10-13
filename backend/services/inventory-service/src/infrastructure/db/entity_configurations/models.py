import uuid
from datetime import datetime

from kernel_platform.outbox.models import Base
from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

# Тот же `Base` (и, значит, `Base.metadata`), что и `kernel_platform`'овский
# `OutboxMessage` (ADR 0010) — так тесты (`Base.metadata.create_all`) и
# написанная вручную Alembic-ревизия видят все таблицы inventory-service
# вместе.


class InventoryModel(Base):
    """PK = `product_id` (ADR 0016, issue #367) — не отдельный синтетический
    id: один Inventory Pool на продукт закреплён уже на уровне схемы.

    `reserved` (issue #370, D2) — денормализованный счётчик зарезервированного
    количества, защищённый той же `SELECT ... FOR UPDATE`, что `adjust()`
    уже использует. `CHECK(reserved <= quantity)` — defense-in-depth рядом с
    доменным инвариантом (`Inventory.adjust()`/`reserve()`)."""

    __tablename__ = "inventory"
    __table_args__ = (
        CheckConstraint(
            "reserved <= quantity", name="ck_inventory_reserved_le_quantity"
        ),
    )
    # `pending_audit_reason` ниже намеренно не использует `Mapped[...]` —
    # разрешаем declarative-сканеру SQLAlchemy 2.0 пропустить его как
    # немаппленный обычный Python-атрибут, а не колонку (см. пояснение там же).
    __allow_unmapped__ = True

    product_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    quantity: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    reserved: Mapped[int] = mapped_column(Integer, default=0, server_default="0")

    # Транзитное поле, не колонка (`__allow_unmapped__` выше). Несёт `reason`
    # из запроса корректировки в audit before_update-listener в рамках
    # одного flush (issue #367) — сам `reason` не персистится в БД.
    pending_audit_reason: str | None = None


class ReservationModel(Base):
    """PK = `order_id` (issue #370, D3) — тот же принцип, что `InventoryModel`:
    «один активный резерв на заказ» закреплён уже на уровне схемы."""

    __tablename__ = "reservations"
    __table_args__ = (
        Index(
            "ix_reservations_active_expires_at",
            "expires_at",
            postgresql_where=text("status = 'active'"),
        ),
    )

    order_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ReservationLineModel(Base):
    """`ON DELETE CASCADE` — удаление резерва удаляет его строки (тот же
    прецедент, что `CartLineModel`, issue #369). `CHECK(quantity > 0)` —
    Always-Valid на уровне БД, продублировано доменной валидацией."""

    __tablename__ = "reservation_lines"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_reservation_lines_quantity_positive"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    reservation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("reservations.order_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    product_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
