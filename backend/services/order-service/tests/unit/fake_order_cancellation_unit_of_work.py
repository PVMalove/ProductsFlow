"""Фейковый UoW отмены заказа для юнит-тестов CancelOrderCommandHandler (ADR
0006, issue #377): только то, что объявляет `OrderCancellationUnitOfWork`."""

from typing import Any

from test_support.unit_of_work import FakeUnitOfWork


class FakeOrderCancellationUnitOfWork(FakeUnitOfWork):
    def __init__(self, *, orders: Any, saga_command_outbox: Any) -> None:
        super().__init__()
        self.orders = orders
        self.saga_command_outbox = saga_command_outbox
