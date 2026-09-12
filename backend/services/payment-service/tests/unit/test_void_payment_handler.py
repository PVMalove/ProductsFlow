"""application/commands/void_payment.py (issue #368, Seams for TDD #4)."""

import uuid

from kernel_platform.security import Actor, ActorRole

from application.commands import VoidPaymentCommand, VoidPaymentCommandHandler
from domain.entities.payment_authorization import PaymentAuthorization
from domain.psp_client import PspAuthorizeOutcome
from tests.unit.fake_payment_repository import FakePaymentAuthorizationRepository
from tests.unit.fake_payment_unit_of_work import FakePaymentUnitOfWork

ACTOR = Actor(id=uuid.uuid4(), role=ActorRole.USER)


def _authorized() -> PaymentAuthorization:
    return PaymentAuthorization.create(
        "auth-key-1", 1000, "success", PspAuthorizeOutcome.SUCCESS
    ).value


async def test_void_succeeds_and_commits() -> None:
    payment = _authorized()
    repo = FakePaymentAuthorizationRepository([payment])
    uow = FakePaymentUnitOfWork(repo)
    handler = VoidPaymentCommandHandler(uow)

    result = await handler.execute(
        VoidPaymentCommand(
            actor=ACTOR, authorization_id=payment.id, idempotency_key="void-key-1"
        )
    )

    assert result.is_ok
    assert result.value.status == "voided"
    assert uow.committed is True
    assert repo.save_calls == [payment]


async def test_void_repeated_with_same_key_is_ok_and_commits_again() -> None:
    payment = _authorized()
    repo = FakePaymentAuthorizationRepository([payment])
    uow = FakePaymentUnitOfWork(repo)
    handler = VoidPaymentCommandHandler(uow)
    command = VoidPaymentCommand(
        actor=ACTOR, authorization_id=payment.id, idempotency_key="void-key-1"
    )
    first = await handler.execute(command)
    assert first.is_ok

    second = await handler.execute(command)

    assert second.is_ok
    assert second.value.status == "voided"


async def test_void_unknown_authorization_fails() -> None:
    repo = FakePaymentAuthorizationRepository()
    uow = FakePaymentUnitOfWork(repo)
    handler = VoidPaymentCommandHandler(uow)

    result = await handler.execute(
        VoidPaymentCommand(
            actor=ACTOR, authorization_id=uuid.uuid4(), idempotency_key="void-key-1"
        )
    )

    assert result.is_err
    assert result.error.code == "authorization_not_found"
    assert uow.committed is False


async def test_void_from_declined_conflicts_without_commit() -> None:
    payment = PaymentAuthorization.create(
        "auth-key-1", 1000, "decline", PspAuthorizeOutcome.DECLINE
    ).value
    repo = FakePaymentAuthorizationRepository([payment])
    uow = FakePaymentUnitOfWork(repo)
    handler = VoidPaymentCommandHandler(uow)

    result = await handler.execute(
        VoidPaymentCommand(
            actor=ACTOR, authorization_id=payment.id, idempotency_key="void-key-1"
        )
    )

    assert result.is_err
    assert result.error.code == "invalid_authorization_state"
    assert uow.committed is False
