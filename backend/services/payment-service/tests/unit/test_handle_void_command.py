# ruff: noqa: E501
"""`api/payment_commands.py::handle_void_command` (issue #371, Seams for TDD
#4) — business branching for the void adapter: successful void of an
AUTHORIZED payment inserts a correlated `payment.voided.v1` OutboxMessage; a
legitimate race/repeat (not found, or already voided under a different
idempotency key) is a silent no-op per D7 — no exception, no outbox row
(mirrors `ReleaseInventoryReservationCommandHandler`, issue #370). Persistence
is faked (`FakePaymentAuthorizationRepository`/`FakePaymentUnitOfWork`, issue
#368's own unit-test fakes) via a monkeypatched `PaymentCommandUnitOfWork`
factory — `consume_command`'s real inbox-dedup guarantee (no second
`command_id` invocation) is proven separately at the integration level
(Seams for TDD #6); this seam only pins `handle_void_command`'s own business
branching."""

import uuid

import pytest
from kernel_platform.commands import Command
from kernel_platform.outbox.models import OutboxMessage

import api.workers.commands.payment_commands as payment_commands
from domain.entities.payment_authorization import (
    PaymentAuthorization,
    PaymentAuthorizationStatus,
)
from domain.psp_client import PspAuthorizeOutcome
from tests.unit.fake_payment_repository import FakePaymentAuthorizationRepository
from tests.unit.fake_payment_unit_of_work import FakePaymentUnitOfWork


class _RecordingSession:
    def __init__(self) -> None:
        self.added: list[object] = []

    def add(self, value: object) -> None:
        self.added.append(value)


def _authorized_payment() -> PaymentAuthorization:
    return PaymentAuthorization.create(
        "auth-key-1", 1000, "success", PspAuthorizeOutcome.SUCCESS
    ).value


def _void_command(authorization_id: uuid.UUID) -> Command:
    return Command(
        command_id=uuid.uuid4(),
        command_type="payment.void.v1",
        causation_id=uuid.uuid4(),
        correlation_id="corr-1",
        payload={"authorization_id": str(authorization_id)},
    )


def _patch_uow(
    monkeypatch: pytest.MonkeyPatch, repo: FakePaymentAuthorizationRepository
) -> None:
    monkeypatch.setattr(
        payment_commands,
        "PaymentCommandUnitOfWork",
        lambda session: FakePaymentUnitOfWork(repo),
    )


async def test_void_of_an_authorized_payment_adds_a_voided_outbox_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payment = _authorized_payment()
    repo = FakePaymentAuthorizationRepository([payment])
    _patch_uow(monkeypatch, repo)
    session = _RecordingSession()
    command = _void_command(payment.id)

    await payment_commands.handle_void_command(session, command)  # type: ignore[arg-type]

    assert len(session.added) == 1
    row = session.added[0]
    assert isinstance(row, OutboxMessage)
    assert row.event_type == "payment.voided.v1"
    assert row.aggregate_type == "PaymentAuthorization"
    assert row.aggregate_id == payment.id
    assert row.payload == {
        "authorization_id": str(payment.id),
        "correlation_id": command.correlation_id,
        "causation_id": str(command.causation_id),
    }
    assert repo.save_calls[-1].status == PaymentAuthorizationStatus.VOIDED


async def test_void_of_an_unknown_authorization_is_a_silent_no_op(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = FakePaymentAuthorizationRepository()
    _patch_uow(monkeypatch, repo)
    session = _RecordingSession()
    command = _void_command(uuid.uuid4())

    await payment_commands.handle_void_command(session, command)  # type: ignore[arg-type]

    assert session.added == []


async def test_void_of_an_already_voided_payment_is_a_silent_no_op(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payment = _authorized_payment()
    payment.void("earlier-void-key")
    assert payment.status == PaymentAuthorizationStatus.VOIDED
    repo = FakePaymentAuthorizationRepository([payment])
    _patch_uow(monkeypatch, repo)
    session = _RecordingSession()
    # A different command_id than the one that produced "earlier-void-key" —
    # a genuinely different void attempt, not a broker redelivery.
    command = _void_command(payment.id)

    await payment_commands.handle_void_command(session, command)  # type: ignore[arg-type]

    assert session.added == []
