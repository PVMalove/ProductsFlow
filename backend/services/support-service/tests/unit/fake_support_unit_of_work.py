"""Fake `SupportUnitOfWork` (ADR 0034, issue #245) — wraps the shared
`FakeUnitOfWork` from test-support with the ticket repository fake each test
constructs, mirroring the generic/per-service split of the real contract."""

from typing import Any

from test_support.unit_of_work import FakeUnitOfWork


class FakeSupportUnitOfWork(FakeUnitOfWork):
    def __init__(self, tickets: Any) -> None:
        super().__init__()
        self.tickets = tickets
