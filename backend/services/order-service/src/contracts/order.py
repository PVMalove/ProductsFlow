"""Framework-independent контракт вывода Order (issue #372, ADR 0002) —
application-хендлеры возвращают его, HTTP только сериализует. Не несёт
`saga_step` — внутренний Saga Step не раскрывается клиенту (ADR 0016:7)."""

import uuid
from dataclasses import dataclass
from datetime import datetime

from domain.entities.order import Order, OrderLine


@dataclass(frozen=True)
class OrderLineView:
    id: uuid.UUID
    product_id: uuid.UUID
    quantity: int
    unit_price_kopecks: int

    @classmethod
    def from_domain(cls, line: OrderLine) -> "OrderLineView":
        return cls(
            id=line.id,
            product_id=line.product_id,
            quantity=line.quantity,
            unit_price_kopecks=line.unit_price_kopecks,
        )


@dataclass(frozen=True)
class OrderView:
    id: uuid.UUID
    status: str
    failure_reason: str | None
    lines: list[OrderLineView]
    created_at: datetime

    @classmethod
    def from_domain(cls, order: Order) -> "OrderView":
        return cls(
            id=order.id,
            status=order.status.value,
            failure_reason=order.failure_reason,
            lines=[OrderLineView.from_domain(line) for line in order.lines],
            created_at=order.created_at,
        )
