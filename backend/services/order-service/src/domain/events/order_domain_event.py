import uuid
from dataclasses import dataclass
from typing import Any

from kernel_domain.domain_event import DomainEvent


@dataclass(frozen=True, kw_only=True)
class OrderCompleted(DomainEvent):
    """Факт успешного завершения Saga checkout (issue #376, D2): capture
    подтверждён, Order `COMPLETED`. Версия — суффикс `.v1` routing key
    (платформенная конвенция); `occurred_at` и trace context добавляет
    `drain_events_to_outbox`.

    Payload нарочно минимален и не несёт `user_id` или иных данных
    покупателя (ADR 0016): `correlation_id` — `str(order_id)`, как у всех
    сообщений Saga; `causation_id` — `causation_id` входящего
    `payment.captured.v1`, т.е. id собственной команды `payment.capture.v1`
    этого Order (UUID, не BigInt `message_id`)."""

    aggregate_type: str = "Order"
    event_type: str = "order.completed.v1"

    order_id: uuid.UUID
    causation_id: uuid.UUID

    def aggregate_id(self) -> uuid.UUID:
        return self.order_id

    def to_payload(self) -> dict[str, Any]:
        return {
            "order_id": str(self.order_id),
            "correlation_id": str(self.order_id),
            "causation_id": str(self.causation_id),
        }
