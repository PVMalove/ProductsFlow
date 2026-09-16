import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from domain.entities.order import OrderLine
from domain.repositories import (
    ReservationOutboxRepository as ReservationOutboxRepositoryPort,
)
from infrastructure.db.entity_configurations.models import ReservationOutboxModel


class ReservationOutboxRepository:
    """Пишущая сторона `reservation_outbox` (issue #372, D6) — используется
    `CheckoutCommandHandler` внутри его транзакции. Дренаж/публикация — забота
    отдельного `ReservationOutboxPublisher` (не этого класса), тот же
    разрыв, что generic `OutboxPublisher` vs доменные `add_domain_event`."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def enqueue(self, *, order_id: uuid.UUID, lines: list[OrderLine]) -> None:
        self.session.add(
            ReservationOutboxModel(
                id=uuid.uuid4(),
                order_id=order_id,
                payload={
                    "order_id": str(order_id),
                    "lines": [
                        {"product_id": str(line.product_id), "quantity": line.quantity}
                        for line in lines
                    ],
                },
            )
        )


_reservation_outbox_repository_implementation: type[ReservationOutboxRepositoryPort] = (
    ReservationOutboxRepository
)
