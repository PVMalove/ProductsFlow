# ruff: noqa: E501
"""Query и handler поиска авторизации по idempotency-ключу (issue #368) —
единственный реалистичный сценарий reconciliation: вызывающий может знать
только ключ, который сам отправил (архитектурный бриф)."""

from dataclasses import dataclass

from kernel_domain.result import Result

from contracts.payment import PaymentAuthorizationView
from domain.errors import PaymentErrors
from domain.repositories import PaymentAuthorizationRepository


@dataclass(frozen=True)
class LookupPaymentQuery:
    idempotency_key: str


class LookupPaymentQueryHandler:
    """
    Business Logic Summary

    Context & Purpose: Поиск авторизации платежа по idempotency-ключу (authorize/void/capture).
    Validations: Нет — чистое чтение.
    Data Sourcing: PaymentAuthorizationRepository.get_by_idempotency_key.
    """

    def __init__(self, repository: PaymentAuthorizationRepository) -> None:
        self._repository = repository

    async def execute(
        self, query: LookupPaymentQuery
    ) -> Result[PaymentAuthorizationView]:
        payment = await self._repository.get_by_idempotency_key(query.idempotency_key)
        if payment is None:
            return Result[PaymentAuthorizationView].fail(
                PaymentErrors.authorization_not_found()
            )
        return Result[PaymentAuthorizationView].ok(
            PaymentAuthorizationView.from_domain(payment)
        )
