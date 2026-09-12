"""application/commands/authorize_payment.py (issue #368, Seams for TDD #4)
— по образцу catalog/inventory's handler тестов: success, конфликт по тому же
ключу с другим телом, идемпотентный повтор без обращения к PSP."""

import uuid

from kernel_platform.security import Actor, ActorRole

from application.commands import AuthorizePaymentCommand, AuthorizePaymentCommandHandler
from contracts.payment import PaymentAuthorizationView
from domain.psp_client import PspAuthorizeOutcome
from tests.unit.fake_payment_repository import FakePaymentAuthorizationRepository
from tests.unit.fake_payment_unit_of_work import FakePaymentUnitOfWork
from tests.unit.fake_psp_client import FakePspClient

ACTOR = Actor(id=uuid.uuid4(), role=ActorRole.USER)


async def test_authorize_success_creates_and_commits() -> None:
    repo = FakePaymentAuthorizationRepository()
    uow = FakePaymentUnitOfWork(repo)
    psp = FakePspClient(authorize_outcome=PspAuthorizeOutcome.SUCCESS)
    handler = AuthorizePaymentCommandHandler(uow, psp)

    result = await handler.execute(
        AuthorizePaymentCommand(
            actor=ACTOR,
            idempotency_key="key-1",
            amount=1000,
            payment_method_token="success",
        )
    )

    assert result.is_ok
    assert result.value.status == "authorized"
    assert result.value.amount == 1000
    assert uow.committed is True
    assert psp.authorize_calls == [("success", 1000)]
    assert len(repo.add_calls) == 1


async def test_authorize_repeated_with_same_key_and_body_does_not_call_psp_again() -> (
    None
):
    repo = FakePaymentAuthorizationRepository()
    uow = FakePaymentUnitOfWork(repo)
    psp = FakePspClient(authorize_outcome=PspAuthorizeOutcome.SUCCESS)
    handler = AuthorizePaymentCommandHandler(uow, psp)
    command = AuthorizePaymentCommand(
        actor=ACTOR,
        idempotency_key="key-1",
        amount=1000,
        payment_method_token="success",
    )
    first = await handler.execute(command)
    assert first.is_ok

    second = await handler.execute(command)

    assert second.is_ok
    assert second.value == first.value
    assert len(psp.authorize_calls) == 1
    assert len(repo.add_calls) == 1


async def test_authorize_repeated_with_same_key_and_different_body_conflicts() -> None:
    repo = FakePaymentAuthorizationRepository()
    uow = FakePaymentUnitOfWork(repo)
    psp = FakePspClient(authorize_outcome=PspAuthorizeOutcome.SUCCESS)
    handler = AuthorizePaymentCommandHandler(uow, psp)
    first = await handler.execute(
        AuthorizePaymentCommand(
            actor=ACTOR,
            idempotency_key="key-1",
            amount=1000,
            payment_method_token="success",
        )
    )
    assert first.is_ok

    second = await handler.execute(
        AuthorizePaymentCommand(
            actor=ACTOR,
            idempotency_key="key-1",
            amount=2000,
            payment_method_token="success",
        )
    )

    assert second.is_err
    assert second.error.code == "idempotency_conflict"
    assert len(psp.authorize_calls) == 1


async def test_authorize_unknown_token_fails_without_creating() -> None:
    repo = FakePaymentAuthorizationRepository()
    uow = FakePaymentUnitOfWork(repo)
    psp = FakePspClient()
    handler = AuthorizePaymentCommandHandler(uow, psp)

    result = await handler.execute(
        AuthorizePaymentCommand(
            actor=ACTOR,
            idempotency_key="key-1",
            amount=1000,
            payment_method_token="not-a-real-scenario",
        )
    )

    assert result.is_err
    assert result.error.code == "unknown_test_scenario_token"
    assert repo.add_calls == []


async def test_authorize_invalid_amount_fails() -> None:
    repo = FakePaymentAuthorizationRepository()
    uow = FakePaymentUnitOfWork(repo)
    psp = FakePspClient()
    handler = AuthorizePaymentCommandHandler(uow, psp)

    result = await handler.execute(
        AuthorizePaymentCommand(
            actor=ACTOR,
            idempotency_key="key-1",
            amount=0,
            payment_method_token="success",
        )
    )

    assert result.is_err
    assert result.error.code == "invalid_amount"


def test_view_is_a_frozen_dataclass() -> None:
    assert hasattr(PaymentAuthorizationView, "__dataclass_fields__")
