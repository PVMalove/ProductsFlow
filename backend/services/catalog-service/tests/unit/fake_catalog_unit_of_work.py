"""Фейковый UoW catalog для юнит-тестов command handler'ов (ADR 0006)."""

from typing import Any

from test_support.unit_of_work import FakeUnitOfWork


class FakeCatalogUnitOfWork(FakeUnitOfWork):
    def __init__(self, products: Any) -> None:
        super().__init__()
        self.products = products
