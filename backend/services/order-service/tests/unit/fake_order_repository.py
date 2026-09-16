"""Фейковый OrderRepository для юнит-тестов application handler'ов
(issue #372)."""

import uuid

from domain.entities.order import Order


class FakeOrderRepository:
    def __init__(self, orders: list[Order] | None = None) -> None:
        self._by_id: dict[uuid.UUID, Order] = {
            order.id: order for order in (orders or [])
        }
        self.save_calls: list[Order] = []

    async def get_by_id(self, order_id: uuid.UUID) -> Order | None:
        return self._by_id.get(order_id)

    async def save(self, order: Order) -> None:
        self.save_calls.append(order)
        self._by_id[order.id] = order
