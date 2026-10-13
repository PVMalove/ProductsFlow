import uuid
from dataclasses import dataclass
from typing import Any

from kernel_domain.domain_event import DomainEvent


@dataclass(frozen=True, kw_only=True)
class InventoryAdjusted(DomainEvent):
    """Аудитируемая корректировка остатка (ADR 0016, issue #367). Сегодня
    без подписчиков — цена canon-parity с транзакционным outbox, окупится
    с появлением order-service/reservation (см. Trade-offs архитектурного
    брифа #367)."""

    aggregate_type: str = "Inventory"
    event_type: str = "inventory.adjusted.v1"

    product_id: uuid.UUID
    delta: int
    quantity_after: int

    def aggregate_id(self) -> uuid.UUID:
        return self.product_id

    def to_payload(self) -> dict[str, Any]:
        return {
            "product_id": str(self.product_id),
            "delta": self.delta,
            "quantity_after": self.quantity_after,
        }
