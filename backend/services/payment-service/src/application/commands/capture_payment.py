# ruff: noqa: E501
"""Команда и handler захвата (capture) авторизованного платежа (issue #368)."""

import logging
import uuid
from dataclasses import dataclass

from kernel_domain.result import Result
from kernel_platform.security import Actor

from contracts.payment import PaymentAuthorizationView
from domain.entities.payment_authorization import PaymentAuthorizationStatus
from domain.errors import PaymentErrors
from domain.psp_client import PspClient
from domain.unit_of_work import PaymentUnitOfWork

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CapturePaymentCommand:
    actor: Actor
    authorization_id: uuid.UUID
    idempotency_key: str


class CapturePaymentCommandHandler:
    """
    Business Logic Summary

    Context & Purpose: Идемпотентный захват ранее авторизованного платежа через Test PSP.
    Validations: Авторизация должна существовать и находиться в статусе AUTHORIZED; повтор до сверки CAPTURE_UNKNOWN другим ключом запрещён (ADR 0016).
    Side Effects: Повторный вызов с тем же idempotency_key не переспрашивает PSP; недопустимые переходы отклоняются без обращения к PSP.
    """

    def __init__(self, uow: PaymentUnitOfWork, psp_client: PspClient) -> None:
        self._uow = uow
        self._psp_client = psp_client

    async def execute(
        self, command: CapturePaymentCommand
    ) -> Result[PaymentAuthorizationView]:
        async with self._uow:
            payment = await self._uow.payments.get_by_id(command.authorization_id)
            if payment is None:
                logger.warning(
                    "Capture отклонён: authorization_id=%s не найден",
                    command.authorization_id,
                )
                return Result[PaymentAuthorizationView].fail(
                    PaymentErrors.authorization_not_found()
                )

            if payment.capture_idempotency_key == command.idempotency_key:
                return Result[PaymentAuthorizationView].ok(
                    PaymentAuthorizationView.from_domain(payment)
                )
            if payment.status is PaymentAuthorizationStatus.CAPTURE_UNKNOWN:
                # Не вызываем PSP впустую для заведомо недопустимого перехода —
                # entity.capture() применил бы тот же код, но здесь дешевле
                # отклонить это раньше (ADR 0016: повтор до сверки запрещён).
                return Result[PaymentAuthorizationView].fail(
                    PaymentErrors.capture_pending_reconciliation()
                )
            if payment.status is not PaymentAuthorizationStatus.AUTHORIZED:
                return Result[PaymentAuthorizationView].fail(
                    PaymentErrors.invalid_authorization_state()
                )

            outcome = await self._psp_client.capture(payment.payment_method_token)
            result = payment.capture(command.idempotency_key, outcome)
            if result.is_err:
                return Result[PaymentAuthorizationView].fail(result.error)

            await self._uow.payments.save(payment)
            await self._uow.commit()

        logger.info(
            "Платёж захвачен: authorization_id=%s status=%s actor=%s",
            command.authorization_id,
            payment.status,
            command.actor.id,
        )
        return Result[PaymentAuthorizationView].ok(
            PaymentAuthorizationView.from_domain(payment)
        )
