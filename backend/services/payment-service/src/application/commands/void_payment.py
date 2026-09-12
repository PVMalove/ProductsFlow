# ruff: noqa: E501
"""Команда и handler отмены авторизации платежа (issue #368). Void не требует
вызова PSP — Test PSP не хранит внешнего состояния, которое нужно было бы
отменять (архитектурный бриф D4)."""

import logging
import uuid
from dataclasses import dataclass

from kernel_domain.result import Result
from kernel_platform.security import Actor

from contracts.payment import PaymentAuthorizationView
from domain.errors import PaymentErrors
from domain.unit_of_work import PaymentUnitOfWork

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class VoidPaymentCommand:
    actor: Actor
    authorization_id: uuid.UUID
    idempotency_key: str


class VoidPaymentCommandHandler:
    """
    Business Logic Summary

    Context & Purpose: Идемпотентная отмена ранее авторизованного платежа.
    Validations: Авторизация должна существовать и находиться в статусе AUTHORIZED (PaymentAuthorization.void).
    Side Effects: Обновляется status/void_idempotency_key в репозитории. PSP не вызывается.
    """

    def __init__(self, uow: PaymentUnitOfWork) -> None:
        self._uow = uow

    async def execute(
        self, command: VoidPaymentCommand
    ) -> Result[PaymentAuthorizationView]:
        async with self._uow:
            payment = await self._uow.payments.get_by_id(command.authorization_id)
            if payment is None:
                logger.warning(
                    "Отмена отклонена: authorization_id=%s не найден",
                    command.authorization_id,
                )
                return Result[PaymentAuthorizationView].fail(
                    PaymentErrors.authorization_not_found()
                )

            result = payment.void(command.idempotency_key)
            if result.is_err:
                logger.warning(
                    "Отмена отклонена: authorization_id=%s code=%s",
                    command.authorization_id,
                    result.error.code,
                )
                return Result[PaymentAuthorizationView].fail(result.error)

            await self._uow.payments.save(payment)
            await self._uow.commit()

        logger.info(
            "Авторизация отменена: authorization_id=%s actor=%s",
            command.authorization_id,
            command.actor.id,
        )
        return Result[PaymentAuthorizationView].ok(
            PaymentAuthorizationView.from_domain(payment)
        )
