"""Catalog fake UoW for command-handler unit tests (ADR 0034)."""

from typing import Any

from test_support.unit_of_work import FakeUnitOfWork


class FakeCatalogUnitOfWork(FakeUnitOfWork):
    def __init__(self, products: Any) -> None:
        super().__init__()
        self.products = products
