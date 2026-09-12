# ruff: noqa: E501
"""Команда и handler создания авторизации платежа (issue #368)."""

import logging
from dataclasses import dataclass

from kernel_domain.result import Result
from kernel_platform.security import Actor

from contracts.payment import PaymentAuthorizationView
from domain.entities.payment_authorization import PaymentAuthorization
from domain.errors import PaymentErrors
from domain.psp_client import PspClient, UnknownPspScenarioTokenError
from domain.unit_of_work import PaymentUnitOfWork

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AuthorizePaymentCommand:
    """DTO для авторизации платежа, идемпотентной по `idempotency_key`."""

    actor: Actor
    idempotency_key: str
    amount: int
    payment_method_token: str


class AuthorizePaymentCommandHandler:
    """
    Business Logic Summary

    Context & Purpose: Идемпотентная авторизация платежа через детерминированный Test PSP.
    Validations: Сумма должна быть положительной (PaymentAuthorization.create); тот же idempotency_key с другим amount/payment_method_token — конфликт.
    Side Effects: Повторный вызов с тем же ключом и телом не переспрашивает PSP и не создаёт новую строку.
    """

    def __init__(self, uow: PaymentUnitOfWork, psp_client: PspClient) -> None:
        self._uow = uow
        self._psp_client = psp_client

    async def execute(
        self, command: AuthorizePaymentCommand
    ) -> Result[PaymentAuthorizationView]:
        async with self._uow:
            existing = await self._uow.payments.get_by_idempotency_key(
                command.idempotency_key
            )
            if existing is not None:
                if (
                    existing.amount != command.amount
                    or existing.payment_method_token != command.payment_method_token
                ):
                    logger.warning(
                        "Авторизация отклонена: idempotency_key=%s уже использован с другим телом",
                        command.idempotency_key,
                    )
                    return Result[PaymentAuthorizationView].fail(
                        PaymentErrors.idempotency_conflict()
                    )
                return Result[PaymentAuthorizationView].ok(
                    PaymentAuthorizationView.from_domain(existing)
                )

            try:
                outcome = await self._psp_client.authorize(
                    command.payment_method_token, command.amount
                )
            except UnknownPspScenarioTokenError:
                return Result[PaymentAuthorizationView].fail(
                    PaymentErrors.unknown_test_scenario_token()
                )

            result = PaymentAuthorization.create(
                command.idempotency_key,
                command.amount,
                command.payment_method_token,
                outcome,
            )
            if result.is_err:
                return Result[PaymentAuthorizationView].fail(result.error)

            payment = result.value
            # Race на первом authorize с новым ключом не закрыт (архитектурный
            # бриф #368, D3 Trade-offs/Risk №3) — намеренно, до интеграции
            # реального PSP; возврат `add()` здесь не проверяется.
            await self._uow.payments.add(payment)
            await self._uow.commit()

        logger.info(
            "Авторизация создана: idempotency_key=%s status=%s actor=%s",
            command.idempotency_key,
            payment.status,
            command.actor.id,
        )
        return Result[PaymentAuthorizationView].ok(
            PaymentAuthorizationView.from_domain(payment)
        )
