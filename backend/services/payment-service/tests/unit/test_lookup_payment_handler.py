"""application/queries/lookup_payment.py (issue #368, Seams for TDD #4) —
lookup по idempotency-ключу, единственный реалистичный сценарий reconciliation
(вызывающий может знать только ключ, который сам отправил)."""

from application.queries import LookupPaymentQuery, LookupPaymentQueryHandler
from domain.entities.payment_authorization import PaymentAuthorization
from domain.psp_client import PspAuthorizeOutcome
from tests.unit.fake_payment_repository import FakePaymentAuthorizationRepository


def _authorized() -> PaymentAuthorization:
    return PaymentAuthorization.create(
        "auth-key-1", 1000, "success", PspAuthorizeOutcome.SUCCESS
    ).value


async def test_lookup_by_authorize_key_returns_view() -> None:
    payment = _authorized()
    repo = FakePaymentAuthorizationRepository([payment])
    handler = LookupPaymentQueryHandler(repo)

    result = await handler.execute(LookupPaymentQuery(idempotency_key="auth-key-1"))

    assert result.is_ok
    assert result.value.id == payment.id


async def test_lookup_by_void_key_returns_view() -> None:
    payment = _authorized()
    payment.void("void-key-1")
    repo = FakePaymentAuthorizationRepository([payment])
    handler = LookupPaymentQueryHandler(repo)

    result = await handler.execute(LookupPaymentQuery(idempotency_key="void-key-1"))

    assert result.is_ok
    assert result.value.status == "voided"


async def test_lookup_unknown_key_fails() -> None:
    repo = FakePaymentAuthorizationRepository()
    handler = LookupPaymentQueryHandler(repo)

    result = await handler.execute(LookupPaymentQuery(idempotency_key="missing"))

    assert result.is_err
    assert result.error.code == "authorization_not_found"
