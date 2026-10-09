# ruff: noqa: E501
"""`api/workers/commands/payment_commands.py::handle_lookup_capture_command`
(issue #374, architect brief D7, TDD seam 4) — business branching for the
reconciliation adapter: a `CAPTURE_UNKNOWN` capture key reaches the PSP lookup
once and emits `payment.captured.v1` (status CAPTURED) or
`payment.capture_not_found.v1` (status AUTHORIZED, absence confirmed); an
already final row emits the same fact without a PSP call; a key that is not a
capture key raises `ValueError` without a PSP call or an outbox row — "not
found locally" is never a confirmation of absence at the PSP. Persistence and
the PSP are faked via monkeypatched `PaymentCommandUnitOfWork`/
`build_psp_client` factories, as in `test_handle_capture_command.py`."""

import uuid

import pytest
from kernel_platform.commands import Command
from kernel_platform.outbox.models import OutboxMessage

import api.workers.commands.payment_commands as payment_commands
from domain.entities.payment_authorization import (
    PaymentAuthorization,
    PaymentAuthorizationStatus,
)
from domain.psp_client import (
    PspAuthorizeOutcome,
    PspCaptureLookupOutcome,
    PspCaptureOutcome,
)
from tests.unit.fake_payment_repository import FakePaymentAuthorizationRepository
from tests.unit.fake_payment_unit_of_work import FakePaymentUnitOfWork
from tests.unit.fake_psp_client import FakePspClient


class _RecordingSession:
    def __init__(self) -> None:
        self.added: list[object] = []

    def add(self, value: object) -> None:
        self.added.append(value)


def _payment_with_capture(outcome: PspCaptureOutcome) -> PaymentAuthorization:
    payment = PaymentAuthorization.create(
        "auth-key-1", 1000, "unknown_capture", PspAuthorizeOutcome.SUCCESS
    ).value
    payment.capture("capture-key-1", outcome)
    return payment


def _lookup_capture_command(idempotency_key: str) -> Command:
    return Command(
        command_id=uuid.uuid4(),
        command_type="payment.lookup_capture.v1",
        causation_id=uuid.uuid4(),
        correlation_id="corr-1",
        payload={"idempotency_key": idempotency_key},
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


def _single_outbox_message(session: _RecordingSession) -> OutboxMessage:
    assert len(session.added) == 1
    row = session.added[0]
    assert isinstance(row, OutboxMessage)
    return row


@pytest.mark.parametrize(
    ("lookup_outcome", "expected_status", "expected_event_type"),
    [
        (
            PspCaptureLookupOutcome.CAPTURED,
            PaymentAuthorizationStatus.CAPTURED,
            "payment.captured.v1",
        ),
        (
            PspCaptureLookupOutcome.NOT_FOUND,
            PaymentAuthorizationStatus.AUTHORIZED,
            "payment.capture_not_found.v1",
        ),
    ],
)
async def test_lookup_of_an_unknown_capture_reconciles_and_adds_the_final_fact(
    monkeypatch: pytest.MonkeyPatch,
    lookup_outcome: PspCaptureLookupOutcome,
    expected_status: PaymentAuthorizationStatus,
    expected_event_type: str,
) -> None:
    payment = _payment_with_capture(PspCaptureOutcome.UNKNOWN)
    repo = FakePaymentAuthorizationRepository([payment])
    psp = FakePspClient(lookup_outcome=lookup_outcome)
    _patch(monkeypatch, repo, psp)
    session = _RecordingSession()
    command = _lookup_capture_command("capture-key-1")

    await payment_commands.handle_lookup_capture_command(session, command)  # type: ignore[arg-type]

    assert psp.lookup_capture_calls == [("unknown_capture", "capture-key-1")]
    assert repo.save_calls[-1].status is expected_status
    row = _single_outbox_message(session)
    assert row.event_type == expected_event_type
    assert row.aggregate_type == "PaymentAuthorization"
    assert row.aggregate_id == payment.id
    assert row.payload == {
        "authorization_id": str(payment.id),
        "correlation_id": command.correlation_id,
        "causation_id": str(command.causation_id),
    }


async def test_lookup_of_a_captured_payment_adds_captured_without_a_psp_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payment = _payment_with_capture(PspCaptureOutcome.CAPTURED)
    repo = FakePaymentAuthorizationRepository([payment])
    psp = FakePspClient()
    _patch(monkeypatch, repo, psp)
    session = _RecordingSession()

    await payment_commands.handle_lookup_capture_command(
        session,  # type: ignore[arg-type]
        _lookup_capture_command("capture-key-1"),
    )

    assert psp.lookup_capture_calls == []
    assert repo.save_calls == []
    assert _single_outbox_message(session).event_type == "payment.captured.v1"


async def test_repeat_lookup_after_confirmed_absence_adds_not_found_without_a_psp_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payment = _payment_with_capture(PspCaptureOutcome.UNKNOWN)
    payment.reconcile_capture("capture-key-1", PspCaptureLookupOutcome.NOT_FOUND)
    repo = FakePaymentAuthorizationRepository([payment])
    psp = FakePspClient()
    _patch(monkeypatch, repo, psp)
    session = _RecordingSession()

    await payment_commands.handle_lookup_capture_command(
        session,  # type: ignore[arg-type]
        _lookup_capture_command("capture-key-1"),
    )

    assert psp.lookup_capture_calls == []
    assert repo.save_calls == []
    assert _single_outbox_message(session).event_type == "payment.capture_not_found.v1"


async def test_lookup_of_a_voided_capture_key_raises_an_explicit_rejection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Confirmed absence -> AUTHORIZED keeps the capture key -> void() -> VOIDED:
    # D7 maps only CAPTURED/AUTHORIZED, so the adapter must reject explicitly
    # (retry/DLQ with a readable reason), not fail on a KeyError.
    payment = _payment_with_capture(PspCaptureOutcome.UNKNOWN)
    payment.reconcile_capture("capture-key-1", PspCaptureLookupOutcome.NOT_FOUND)
    payment.void("void-key-1")
    repo = FakePaymentAuthorizationRepository([payment])
    psp = FakePspClient()
    _patch(monkeypatch, repo, psp)
    session = _RecordingSession()

    with pytest.raises(
        ValueError, match="payment.lookup_capture.v1 rejected: unexpected status voided"
    ):
        await payment_commands.handle_lookup_capture_command(
            session,  # type: ignore[arg-type]
            _lookup_capture_command("capture-key-1"),
        )

    assert psp.lookup_capture_calls == []
    assert session.added == []


async def test_lookup_of_an_unknown_key_raises_without_a_psp_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = FakePaymentAuthorizationRepository()
    psp = FakePspClient()
    _patch(monkeypatch, repo, psp)
    session = _RecordingSession()

    with pytest.raises(ValueError, match="authorization_not_found"):
        await payment_commands.handle_lookup_capture_command(
            session,  # type: ignore[arg-type]
            _lookup_capture_command("capture-key-1"),
        )

    assert psp.lookup_capture_calls == []
    assert session.added == []
