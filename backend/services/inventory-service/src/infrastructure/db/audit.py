import enum
import uuid
from datetime import datetime

from kernel_platform.outbox.models import Base
from observability.context import actor_id_var
from sqlalchemy import BigInteger, Identity, Text, event, func, insert, inspect
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Mapped, Mapper, mapped_column

from infrastructure.db.entity_configurations.models import InventoryModel


class InventoryAuditAction(enum.StrEnum):
    ADJUSTED = "adjusted"


class InventoryAuditLog(Base):
    """Audit-лог корректировок остатка (ADR 0016, issue #367). `product_id`
    — намеренно без FK: Inventory-строка (и её audit-история) переживает
    деактивацию/удаление Product (ADR 0016 подтверждает это явно), а `products`
    вдобавок живёт в другой БД — межбазовый FK физически невозможен."""

    __tablename__ = "inventory_audit_log"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    product_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    # Текст сохраняет и исторические integer actor IDs, и UUID из identity-service
    # (тот же приём, что и `ProductAuditLog.actor_user_id`).
    actor_user_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    action: Mapped[InventoryAuditAction] = mapped_column(Text)
    description: Mapped[str] = mapped_column(Text, default="", server_default="")
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


@event.listens_for(InventoryModel, "before_update")
def _on_inventory_update(
    _mapper: Mapper[InventoryModel], connection: Connection, target: InventoryModel
) -> None:
    state = inspect(target)
    history = state.attrs.quantity.history
    if not history.has_changes():
        return

    old_value = history.deleted[0] if history.deleted else None
    new_value = target.quantity
    delta = new_value - old_value if old_value is not None else new_value
    reason = target.pending_audit_reason or ""

    connection.execute(
        insert(InventoryAuditLog).values(
            action=InventoryAuditAction.ADJUSTED,
            product_id=target.product_id,
            actor_user_id=_actor_for_audit(),
            description=(
                f"Скорректирован остаток товара {target.product_id}: "
                f"{old_value} -> {new_value} (delta={delta:+d}, reason={reason!r})"
            ),
        )
    )


def _actor_for_audit() -> str | None:
    actor = actor_id_var.get()
    return None if actor is None else str(actor)
