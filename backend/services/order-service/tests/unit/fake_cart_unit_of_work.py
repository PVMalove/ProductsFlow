"""Фейковый UoW cart для юнит-тестов command/query handler'ов (ADR 0006)."""

from typing import Any

from test_support.unit_of_work import FakeUnitOfWork


class FakeCartUnitOfWork(FakeUnitOfWork):
    def __init__(self, carts: Any) -> None:
        super().__init__()
        self.carts = carts
