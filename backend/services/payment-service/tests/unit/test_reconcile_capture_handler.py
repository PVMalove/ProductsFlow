"""application/commands/reconcile_capture.py (issue #374, architect brief D5,
TDD seam 3) — command-side reconciliation of an unknown capture by its
idempotency key: only a `CAPTURE_UNKNOWN` row reaches the PSP lookup; an
already final row returns its fact without a PSP call or a write; a key that
is not a capture key is `authorization_not_found` without a PSP call."""

import uuid

from kernel_platform.security import Actor, ActorRole

from application.commands import CapturePaymentCommand, CapturePaymentCommandHandler
from application.commands.reconcile_capture import (
    ReconcileCaptureCommand,
    ReconcileCaptureCommandHandler,
)
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

ACTOR = Actor(id=uuid.uuid4(), role=ActorRole.USER)


def _payment_with_capture(outcome: PspCaptureOutcome) -> PaymentAuthorization:
    payment = PaymentAuthorization.create(
        "auth-key-1", 1000, "unknown_capture", PspAuthorizeOutcome.SUCCESS
    ).value
    payment.capture("capture-key-1", outcome)
    return payment


async def test_reconcile_found_capture_calls_lookup_once_and_captures() -> None:
    payment = _payment_with_capture(PspCaptureOutcome.UNKNOWN)
    repo = FakePaymentAuthorizationRepository([payment])
    uow = FakePaymentUnitOfWork(repo)
    psp = FakePspClient(lookup_outcome=PspCaptureLookupOutcome.CAPTURED)
    handler = ReconcileCaptureCommandHandler(uow, psp)

    result = await handler.execute(
        ReconcileCaptureCommand(actor=ACTOR, idempotency_key="capture-key-1")
    )

    assert result.is_ok
    assert result.value.id == payment.id
    assert result.value.status == "captured"
    assert psp.lookup_capture_calls == [("unknown_capture", "capture-key-1")]
    assert repo.save_calls[-1].status is PaymentAuthorizationStatus.CAPTURED
    assert uow.committed is True


async def test_reconcile_absent_capture_returns_the_authorization_to_authorized() -> (
    None
):
    payment = _payment_with_capture(PspCaptureOutcome.UNKNOWN)
    repo = FakePaymentAuthorizationRepository([payment])
    uow = FakePaymentUnitOfWork(repo)
    psp = FakePspClient(lookup_outcome=PspCaptureLookupOutcome.NOT_FOUND)
    handler = ReconcileCaptureCommandHandler(uow, psp)

    result = await handler.execute(
        ReconcileCaptureCommand(actor=ACTOR, idempotency_key="capture-key-1")
    )

    assert result.is_ok
    assert result.value.status == "authorized"
    assert len(psp.lookup_capture_calls) == 1
    assert repo.save_calls[-1].status is PaymentAuthorizationStatus.AUTHORIZED
    assert uow.committed is True


async def test_new_capture_key_reaches_the_psp_only_after_confirmed_absence() -> None:
    """Issue #374, DoD 3 across both handlers: before reconciliation a new key
    is rejected without a PSP call; after `NOT_FOUND` it reaches the PSP."""
    payment = _payment_with_capture(PspCaptureOutcome.UNKNOWN)
    repo = FakePaymentAuthorizationRepository([payment])
    psp = FakePspClient(
        capture_outcome=PspCaptureOutcome.CAPTURED,
        lookup_outcome=PspCaptureLookupOutcome.NOT_FOUND,
    )
    capture = CapturePaymentCommandHandler(FakePaymentUnitOfWork(repo), psp)
    new_key_capture = CapturePaymentCommand(
        actor=ACTOR, authorization_id=payment.id, idempotency_key="capture-key-2"
    )

    blocked = await capture.execute(new_key_capture)

    assert blocked.is_err
    assert blocked.error.code == "capture_pending_reconciliation"
    assert psp.capture_calls == []

    reconciled = await ReconcileCaptureCommandHandler(
        FakePaymentUnitOfWork(repo), psp
    ).execute(ReconcileCaptureCommand(actor=ACTOR, idempotency_key="capture-key-1"))
    assert reconciled.is_ok

    recaptured = await capture.execute(new_key_capture)

    assert recaptured.is_ok
    assert recaptured.value.status == "captured"
    assert psp.capture_idempotency_keys == ["capture-key-2"]


async def test_reconcile_of_an_already_final_capture_skips_the_psp_and_the_write() -> (
    None
):
    payment = _payment_with_capture(PspCaptureOutcome.CAPTURED)
    repo = FakePaymentAuthorizationRepository([payment])
    uow = FakePaymentUnitOfWork(repo)
    psp = FakePspClient(lookup_outcome=PspCaptureLookupOutcome.NOT_FOUND)
    handler = ReconcileCaptureCommandHandler(uow, psp)

    result = await handler.execute(
        ReconcileCaptureCommand(actor=ACTOR, idempotency_key="capture-key-1")
    )

    assert result.is_ok
    assert result.value.status == "captured"
    assert psp.lookup_capture_calls == []
    assert repo.save_calls == []
    assert uow.committed is False


async def test_reconcile_of_an_unknown_key_fails_without_a_psp_call() -> None:
    repo = FakePaymentAuthorizationRepository()
    uow = FakePaymentUnitOfWork(repo)
    psp = FakePspClient()
    handler = ReconcileCaptureCommandHandler(uow, psp)

    result = await handler.execute(
        ReconcileCaptureCommand(actor=ACTOR, idempotency_key="capture-key-1")
    )

    assert result.is_err
    assert result.error.code == "authorization_not_found"
    assert psp.lookup_capture_calls == []


async def test_reconcile_by_a_non_capture_key_fails_without_a_psp_call() -> None:
    payment = _payment_with_capture(PspCaptureOutcome.UNKNOWN)
    repo = FakePaymentAuthorizationRepository([payment])
    uow = FakePaymentUnitOfWork(repo)
    psp = FakePspClient()
    handler = ReconcileCaptureCommandHandler(uow, psp)

    result = await handler.execute(
        ReconcileCaptureCommand(actor=ACTOR, idempotency_key="auth-key-1")
    )

    assert result.is_err
    assert result.error.code == "authorization_not_found"
    assert psp.lookup_capture_calls == []
    assert payment.status is PaymentAuthorizationStatus.CAPTURE_UNKNOWN
