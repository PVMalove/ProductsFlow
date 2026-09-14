# ruff: noqa: E501
"""`api/payment_commands.py::handle_authorize_command` (issue #371, Seams for
TDD #4) — business branching for the authorize adapter: `view.status` maps to
one of three distinct result event types (D2/finding 9 — decline/timeout are
`Result.ok`, not `Result.fail`, so the mapping goes by status, not by
`is_err`); a rejected command (`invalid_amount`/`unknown_test_scenario_token`/
`idempotency_conflict`) raises `ValueError` so `consume()`'s retry/DLQ ladder
handles it as a producer bug (D7). Persistence and the PSP are faked
(`FakePaymentAuthorizationRepository`/`FakePaymentUnitOfWork`/`FakePspClient`,
issue #368's own unit-test fakes) via monkeypatched `PaymentCommandUnitOfWork`/
`build_psp_client` factories — the same technique as
`test_handle_void_command.py`."""

import uuid

import pytest
from kernel_platform.commands import Command
from kernel_platform.outbox.models import OutboxMessage

import api.payment_commands as payment_commands
from domain.psp_client import PspAuthorizeOutcome
from tests.unit.fake_payment_repository import FakePaymentAuthorizationRepository
from tests.unit.fake_payment_unit_of_work import FakePaymentUnitOfWork
from tests.unit.fake_psp_client import FakePspClient


class _RecordingSession:
    def __init__(self) -> None:
        self.added: list[object] = []

    def add(self, value: object) -> None:
        self.added.append(value)


def _authorize_command(
    *, amount: int = 1000, payment_method_token: str = "success"
) -> Command:
    return Command(
        command_id=uuid.uuid4(),
        command_type="payment.authorize.v1",
        causation_id=uuid.uuid4(),
        correlation_id="corr-1",
        payload={"amount": amount, "payment_method_token": payment_method_token},
    )


def _patch_uow(
    monkeypatch: pytest.MonkeyPatch, repo: FakePaymentAuthorizationRepository
) -> None:
    monkeypatch.setattr(
        payment_commands,
        "PaymentCommandUnitOfWork",
        lambda session: FakePaymentUnitOfWork(repo),
    )


def _patch_psp(monkeypatch: pytest.MonkeyPatch, psp: FakePspClient) -> None:
    monkeypatch.setattr(payment_commands, "build_psp_client", lambda settings: psp)


async def test_successful_authorize_adds_an_authorized_outbox_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = FakePaymentAuthorizationRepository()
    _patch_uow(monkeypatch, repo)
    _patch_psp(monkeypatch, FakePspClient(authorize_outcome=PspAuthorizeOutcome.SUCCESS))
    session = _RecordingSession()
    command = _authorize_command(payment_method_token="success")

    await payment_commands.handle_authorize_command(session, command)  # type: ignore[arg-type]

    assert len(repo.add_calls) == 1
    authorization_id = repo.add_calls[0].id
    assert len(session.added) == 1
    row = session.added[0]
    assert isinstance(row, OutboxMessage)
    assert row.event_type == "payment.authorized.v1"
    assert row.aggregate_type == "PaymentAuthorization"
    assert row.aggregate_id == authorization_id
    assert row.payload == {
        "authorization_id": str(authorization_id),
        "correlation_id": command.correlation_id,
        "causation_id": str(command.causation_id),
    }


async def test_declined_authorize_adds_a_declined_outbox_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = FakePaymentAuthorizationRepository()
    _patch_uow(monkeypatch, repo)
    _patch_psp(monkeypatch, FakePspClient(authorize_outcome=PspAuthorizeOutcome.DECLINE))
    session = _RecordingSession()
    command = _authorize_command(payment_method_token="decline")

    await payment_commands.handle_authorize_command(session, command)  # type: ignore[arg-type]

    assert len(session.added) == 1
    row = session.added[0]
    assert isinstance(row, OutboxMessage)
    assert row.event_type == "payment.authorization_declined.v1"


async def test_timed_out_authorize_adds_a_timed_out_outbox_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = FakePaymentAuthorizationRepository()
    _patch_uow(monkeypatch, repo)
    _patch_psp(monkeypatch, FakePspClient(authorize_outcome=PspAuthorizeOutcome.TIMEOUT))
    session = _RecordingSession()
    command = _authorize_command(payment_method_token="timeout")

    await payment_commands.handle_authorize_command(session, command)  # type: ignore[arg-type]

    assert len(session.added) == 1
    row = session.added[0]
    assert isinstance(row, OutboxMessage)
    assert row.event_type == "payment.authorization_timed_out.v1"


async def test_invalid_amount_raises_and_adds_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = FakePaymentAuthorizationRepository()
    _patch_uow(monkeypatch, repo)
    psp = FakePspClient(authorize_outcome=PspAuthorizeOutcome.SUCCESS)
    _patch_psp(monkeypatch, psp)
    session = _RecordingSession()
    command = _authorize_command(amount=0, payment_method_token="success")

    with pytest.raises(ValueError):
        await payment_commands.handle_authorize_command(session, command)  # type: ignore[arg-type]

    # Deviation from the brief's seam-4 prose ("amount=0 -> ... фейковый PSP
    # не вызывается"): the existing, unmodified
    # AuthorizePaymentCommandHandler.execute() (issue #368) calls the PSP
    # BEFORE PaymentAuthorization.create() validates amount<=0 — so the PSP
    # genuinely IS called once here; it just never gets a chance to persist
    # anything. See the developer report for why this isn't "fixed" here.
    assert len(psp.authorize_calls) == 1
    assert repo.add_calls == []
    assert session.added == []
