# ruff: noqa: E501
"""`infrastructure/db/unit_of_work.py::PaymentCommandUnitOfWork` (issue #371,
Seams for TDD #3) — pins the no-op `commit()`/`__aexit__` contract required by
D5: neither method may touch the underlying session's own `commit()`/
`rollback()`, since `consume_command`'s own `async with session.begin():`
already owns that transaction. The real end-to-end proof that this actually
lets `consume_command` roll back everything on a mid-transaction failure is
the integration-level seam #1
(tests/integration/test_payment_outbox_inbox_atomicity.py) — this unit test
only pins the mechanics precisely, with a spy in place of a real session
(mirrors kernel-platform's own `test_outbox_drain.py::_RecordingSession`)."""

import pytest

from infrastructure.db.unit_of_work import PaymentCommandUnitOfWork


class _SpySession:
    def __init__(self) -> None:
        self.commit_calls = 0
        self.rollback_calls = 0

    async def commit(self) -> None:
        self.commit_calls += 1

    async def rollback(self) -> None:
        self.rollback_calls += 1


async def test_commit_does_not_touch_the_underlying_session() -> None:
    session = _SpySession()
    uow = PaymentCommandUnitOfWork(session)  # type: ignore[arg-type]

    await uow.commit()

    assert session.commit_calls == 0


async def test_aexit_never_rolls_back_the_session_on_a_clean_exit() -> None:
    session = _SpySession()
    uow = PaymentCommandUnitOfWork(session)  # type: ignore[arg-type]

    await uow.__aexit__(None, None, None)

    assert session.rollback_calls == 0


async def test_an_exception_raised_inside_the_context_still_propagates() -> None:
    """`__aexit__` must never suppress a pending exception — it has to
    propagate untouched to `consume_command`'s `session.begin()`, the only
    real rollback in this flow (D5)."""
    session = _SpySession()
    uow = PaymentCommandUnitOfWork(session)  # type: ignore[arg-type]

    with pytest.raises(RuntimeError, match="boom"):
        async with uow:
            raise RuntimeError("boom")

    assert session.rollback_calls == 0


async def test_payments_repository_is_wired_to_the_given_session() -> None:
    from infrastructure.db.payment_repository import (
        PaymentAuthorizationRepository as SqlPaymentAuthorizationRepository,
    )

    session = _SpySession()
    uow = PaymentCommandUnitOfWork(session)  # type: ignore[arg-type]

    assert isinstance(uow.payments, SqlPaymentAuthorizationRepository)
    assert uow.payments.session is session  # type: ignore[attr-defined]
