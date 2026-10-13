"""Фейковый UoW inventory для юнит-тестов command handler'ов (ADR 0006)."""

from typing import Any

from test_support.unit_of_work import FakeUnitOfWork


class FakeInventoryUnitOfWork(FakeUnitOfWork):
    def __init__(self, inventory: Any) -> None:
        super().__init__()
        self.inventory = inventory
