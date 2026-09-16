"""Фейковый UoW checkout для юнит-тестов CheckoutCommandHandler (ADR 0006,
issue #372)."""

from typing import Any

from test_support.unit_of_work import FakeUnitOfWork


class FakeCheckoutUnitOfWork(FakeUnitOfWork):
    def __init__(
        self,
        *,
        carts: Any,
        orders: Any,
        idempotency_keys: Any,
        reservation_outbox: Any,
    ) -> None:
        super().__init__()
        self.carts = carts
        self.orders = orders
        self.idempotency_keys = idempotency_keys
        self.reservation_outbox = reservation_outbox
