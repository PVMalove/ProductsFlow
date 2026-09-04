"""Фейковый `SupportUnitOfWork` (ADR 0006, issue #245) — оборачивает общий
`FakeUnitOfWork` из test-support фейком репозитория тикетов, который
конструирует каждый тест, зеркаля generic/per-service разделение реального
контракта."""

from typing import Any

from test_support.unit_of_work import FakeUnitOfWork


class FakeSupportUnitOfWork(FakeUnitOfWork):
    def __init__(self, tickets: Any) -> None:
        super().__init__()
        self.tickets = tickets
