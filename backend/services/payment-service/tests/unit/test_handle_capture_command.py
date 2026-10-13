# ruff: noqa: E501
"""`api/workers/commands/payment_commands.py::handle_capture_command` (issue
#374, architect brief D7, TDD seam 4) — business branching for the capture
adapter: a capture of an AUTHORIZED payment maps `view.status` to one
correlated fact (`payment.captured.v1` / `payment.capture_unknown.v1`) and
persists `capture_idempotency_key = str(command_id)`; every rejection
(`authorization_not_found`, `invalid_authorization_state`,
`capture_pending_reconciliation`) raises `ValueError` so `consume()`'s
retry/DLQ ladder handles it as a producer defect — without a PSP call, a
write or an outbox row. Persistence and the PSP are faked via monkeypatched
`PaymentCommandUnitOfWork`/`build_psp_client` factories, the same technique
as `test_handle_authorize_command.py`."""

import uuid

import pytest
from kernel_platform.commands import Command
from kernel_platform.outbox.models import OutboxMessage

import api.workers.commands.payment_commands as payment_commands
from domain.entities.payment_authorization import (
    PaymentAuthorization,
    PaymentAuthorizationStatus,
)
from domain.psp_client import PspAuthorizeOutcome, PspCaptureOutcome
from tests.unit.fake_payment_repository import FakePaymentAuthorizationRepository
from tests.unit.fake_payment_unit_of_work import FakePaymentUnitOfWork
from tests.unit.fake_psp_client import FakePspClient


class _RecordingSession:
    def __init__(self) -> None:
        self.added: list[object] = []

    def add(self, value: object) -> None:
        self.added.append(value)


def _authorized_payment() -> PaymentAuthorization:
    return PaymentAuthorization.create(
        "auth-key-1", 1000, "success", PspAuthorizeOutcome.SUCCESS
    ).value


def _capture_command(authorization_id: uuid.UUID) -> Command:
    return Command(
        command_id=uuid.uuid4(),
        command_type="payment.capture.v1",
        causation_id=uuid.uuid4(),
        correlation_id="corr-1",
        payload={"authorization_id": str(authorization_id)},
    )


def _patch(
    monkeypatch: pytest.MonkeyPatch,
    repo: FakePaymentAuthorizationRepository,
    psp: FakePspClient,
) -> None:
    monkeypatch.setattr(
        payment_commands,
        "PaymentCommandUnitOfWork",
        lambda session: FakePaymentUnitOfWork(repo),
    )
    monkeypatch.setattr(payment_commands, "build_psp_client", lambda settings: psp)


@pytest.mark.parametrize(
    ("capture_outcome", "expected_status", "expected_event_type"),
    [
        (
            PspCaptureOutcome.CAPTURED,
            PaymentAuthorizationStatus.CAPTURED,
            "payment.captured.v1",
        ),
        (
            PspCaptureOutcome.UNKNOWN,
            PaymentAuthorizationStatus.CAPTURE_UNKNOWN,
            "payment.capture_unknown.v1",
        ),
    ],
)
async def test_capture_of_an_authorized_payment_adds_the_matching_outbox_message(
    monkeypatch: pytest.MonkeyPatch,
    capture_outcome: PspCaptureOutcome,
    expected_status: PaymentAuthorizationStatus,
    expected_event_type: str,
) -> None:
    payment = _authorized_payment()
    repo = FakePaymentAuthorizationRepository([payment])
    psp = FakePspClient(capture_outcome=capture_outcome)
    _patch(monkeypatch, repo, psp)
    session = _RecordingSession()
    command = _capture_command(payment.id)

    await payment_commands.handle_capture_command(session, command)  # type: ignore[arg-type]

    assert psp.capture_calls == ["success"]
    assert repo.save_calls[-1].status is expected_status
    assert repo.save_calls[-1].capture_idempotency_key == str(command.command_id)
    assert len(session.added) == 1
    row = session.added[0]
    assert isinstance(row, OutboxMessage)
    assert row.event_type == expected_event_type
    assert row.aggregate_type == "PaymentAuthorization"
    assert row.aggregate_id == payment.id
    assert row.payload == {
        "authorization_id": str(payment.id),
        "correlation_id": command.correlation_id,
        "causation_id": str(command.causation_id),
    }


async def test_capture_of_an_unknown_authorization_raises_without_a_psp_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = FakePaymentAuthorizationRepository()
    psp = FakePspClient()
    _patch(monkeypatch, repo, psp)
    session = _RecordingSession()

    with pytest.raises(ValueError, match="authorization_not_found"):
        await payment_commands.handle_capture_command(
            session,  # type: ignore[arg-type]
            _capture_command(uuid.uuid4()),
        )

    assert psp.capture_calls == []
    assert repo.save_calls == []
    assert session.added == []


async def test_capture_of_a_non_authorized_payment_raises_without_a_psp_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payment = _authorized_payment()
    payment.void("void-key-1")
    repo = FakePaymentAuthorizationRepository([payment])
    psp = FakePspClient()
    _patch(monkeypatch, repo, psp)
    session = _RecordingSession()

    with pytest.raises(ValueError, match="invalid_authorization_state"):
        await payment_commands.handle_capture_command(
            session,  # type: ignore[arg-type]
            _capture_command(payment.id),
        )

    assert psp.capture_calls == []
    assert repo.save_calls == []
    assert payment.status is PaymentAuthorizationStatus.VOIDED
    assert payment.capture_idempotency_key is None
    assert session.added == []


async def test_capture_with_a_new_key_before_reconciliation_raises_without_a_psp_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payment = _authorized_payment()
    payment.capture("earlier-capture-key", PspCaptureOutcome.UNKNOWN)
    repo = FakePaymentAuthorizationRepository([payment])
    psp = FakePspClient()
    _patch(monkeypatch, repo, psp)
    session = _RecordingSession()

    with pytest.raises(ValueError, match="capture_pending_reconciliation"):
        await payment_commands.handle_capture_command(
            session,  # type: ignore[arg-type]
            _capture_command(payment.id),
        )

    assert psp.capture_calls == []
    assert repo.save_calls == []
    assert payment.status is PaymentAuthorizationStatus.CAPTURE_UNKNOWN
    assert payment.capture_idempotency_key == "earlier-capture-key"
    assert session.added == []
