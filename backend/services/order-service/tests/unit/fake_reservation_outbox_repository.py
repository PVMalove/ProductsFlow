"""Фейковый ReservationOutboxRepository для юнит-тестов (issue #372)."""

import uuid

from domain.entities.order import OrderLine


class FakeReservationOutboxRepository:
    def __init__(self) -> None:
        self.enqueue_calls: list[tuple[uuid.UUID, list[OrderLine]]] = []

    async def enqueue(self, *, order_id: uuid.UUID, lines: list[OrderLine]) -> None:
        self.enqueue_calls.append((order_id, lines))
