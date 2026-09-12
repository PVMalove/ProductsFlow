"""Фейковый UoW payment для юнит-тестов command/query handler'ов (ADR 0006)."""

from typing import Any

from test_support.unit_of_work import FakeUnitOfWork


class FakePaymentUnitOfWork(FakeUnitOfWork):
    def __init__(self, payments: Any) -> None:
        super().__init__()
        self.payments = payments
