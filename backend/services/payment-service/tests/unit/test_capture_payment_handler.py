"""application/commands/capture_payment.py (issue #368, Seams for TDD #4) —
ключевая проверка: при повторном idempotency-ключе фейковый PspClient не
вызывается."""

import uuid

from kernel_platform.security import Actor, ActorRole

from application.commands import CapturePaymentCommand, CapturePaymentCommandHandler
from domain.entities.payment_authorization import PaymentAuthorization
from domain.psp_client import PspAuthorizeOutcome, PspCaptureOutcome
from tests.unit.fake_payment_repository import FakePaymentAuthorizationRepository
from tests.unit.fake_payment_unit_of_work import FakePaymentUnitOfWork
from tests.unit.fake_psp_client import FakePspClient

ACTOR = Actor(id=uuid.uuid4(), role=ActorRole.USER)


def _authorized() -> PaymentAuthorization:
    return PaymentAuthorization.create(
        "auth-key-1", 1000, "success", PspAuthorizeOutcome.SUCCESS
    ).value


async def test_capture_success_calls_psp_once_and_commits() -> None:
    payment = _authorized()
    repo = FakePaymentAuthorizationRepository([payment])
    uow = FakePaymentUnitOfWork(repo)
    psp = FakePspClient(capture_outcome=PspCaptureOutcome.CAPTURED)
    handler = CapturePaymentCommandHandler(uow, psp)

    result = await handler.execute(
        CapturePaymentCommand(
            actor=ACTOR, authorization_id=payment.id, idempotency_key="capture-key-1"
        )
    )

    assert result.is_ok
    assert result.value.status == "captured"
    assert uow.committed is True
    assert psp.capture_calls == ["success"]


async def test_capture_repeated_with_same_key_does_not_call_psp_again() -> None:
    payment = _authorized()
    repo = FakePaymentAuthorizationRepository([payment])
    uow = FakePaymentUnitOfWork(repo)
    psp = FakePspClient(capture_outcome=PspCaptureOutcome.CAPTURED)
    handler = CapturePaymentCommandHandler(uow, psp)
    command = CapturePaymentCommand(
        actor=ACTOR, authorization_id=payment.id, idempotency_key="capture-key-1"
    )
    first = await handler.execute(command)
    assert first.is_ok

    second = await handler.execute(command)

    assert second.is_ok
    assert len(psp.capture_calls) == 1


async def test_capture_unknown_then_new_key_is_blocked_without_psp_call() -> None:
    payment = _authorized()
    repo = FakePaymentAuthorizationRepository([payment])
    uow = FakePaymentUnitOfWork(repo)
    psp = FakePspClient(capture_outcome=PspCaptureOutcome.UNKNOWN)
    handler = CapturePaymentCommandHandler(uow, psp)
    first = await handler.execute(
        CapturePaymentCommand(
            actor=ACTOR, authorization_id=payment.id, idempotency_key="capture-key-1"
        )
    )
    assert first.is_ok
    assert first.value.status == "capture_unknown"

    second = await handler.execute(
        CapturePaymentCommand(
            actor=ACTOR, authorization_id=payment.id, idempotency_key="capture-key-2"
        )
    )

    assert second.is_err
    assert second.error.code == "capture_pending_reconciliation"
    assert len(psp.capture_calls) == 1


async def test_capture_unknown_authorization_fails() -> None:
    repo = FakePaymentAuthorizationRepository()
    uow = FakePaymentUnitOfWork(repo)
    psp = FakePspClient()
    handler = CapturePaymentCommandHandler(uow, psp)

    result = await handler.execute(
        CapturePaymentCommand(
            actor=ACTOR, authorization_id=uuid.uuid4(), idempotency_key="capture-key-1"
        )
    )

    assert result.is_err
    assert result.error.code == "authorization_not_found"
    assert psp.capture_calls == []


async def test_capture_from_non_authorized_state_conflicts_without_calling_psp() -> (
    None
):
    payment = PaymentAuthorization.create(
        "auth-key-1", 1000, "decline", PspAuthorizeOutcome.DECLINE
    ).value
    repo = FakePaymentAuthorizationRepository([payment])
    uow = FakePaymentUnitOfWork(repo)
    psp = FakePspClient()
    handler = CapturePaymentCommandHandler(uow, psp)

    result = await handler.execute(
        CapturePaymentCommand(
            actor=ACTOR, authorization_id=payment.id, idempotency_key="capture-key-1"
        )
    )

    assert result.is_err
    assert result.error.code == "invalid_authorization_state"
    assert psp.capture_calls == []
