"""Фейковый UoW identity для юнит-тестов command handler'ов (ADR 0006)."""

from typing import Any

from test_support.unit_of_work import FakeUnitOfWork


class FakeIdentityUnitOfWork(FakeUnitOfWork):
    def __init__(self, users: Any) -> None:
        super().__init__()
        self.users = users
