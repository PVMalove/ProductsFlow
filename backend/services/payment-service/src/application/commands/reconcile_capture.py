# ruff: noqa: E501
"""Команда и handler сверки неизвестного исхода capture по idempotency-ключу
(issue #374)."""

import logging
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
class ReconcileCaptureCommand:
    actor: Actor
    idempotency_key: str


class ReconcileCaptureCommandHandler:
    """
    Business Logic Summary

    Context & Purpose: Сверка capture в статусе CAPTURE_UNKNOWN у Test PSP по idempotency-ключу (ADR 0016): окончательный факт — захвачен или отсутствие подтверждено.
    Validations: Ключ должен быть capture-ключом существующей авторизации — иначе authorization_not_found без обращения к PSP.
    Side Effects: PSP опрашивается только для CAPTURE_UNKNOWN; подтверждённое отсутствие возвращает авторизацию в AUTHORIZED; уже окончательный статус возвращается без PSP-вызова и без записи.
    """

    def __init__(self, uow: PaymentUnitOfWork, psp_client: PspClient) -> None:
        self._uow = uow
        self._psp_client = psp_client

    async def execute(
        self, command: ReconcileCaptureCommand
    ) -> Result[PaymentAuthorizationView]:
        async with self._uow:
            found = await self._uow.payments.get_by_idempotency_key(
                command.idempotency_key
            )
            # Повторное чтение под блокировкой строки: конкурентная сверка той
            # же авторизации ждёт здесь и видит уже окончательный статус.
            payment = (
                await self._uow.payments.get_by_id(found.id)
                if found is not None
                else None
            )
            if (
                payment is None
                or payment.capture_idempotency_key != command.idempotency_key
            ):
                logger.warning(
                    "Сверка capture отклонена: ключ не является capture-ключом авторизации"
                )
                return Result[PaymentAuthorizationView].fail(
                    PaymentErrors.authorization_not_found()
                )

            if payment.status is PaymentAuthorizationStatus.CAPTURE_UNKNOWN:
                outcome = await self._psp_client.lookup_capture(
                    payment.payment_method_token, command.idempotency_key
                )
                result = payment.reconcile_capture(command.idempotency_key, outcome)
                if result.is_err:
                    return Result[PaymentAuthorizationView].fail(result.error)

                await self._uow.payments.save(payment)
                await self._uow.commit()
                logger.info(
                    "Capture сверен: authorization_id=%s status=%s actor=%s",
                    payment.id,
                    payment.status,
                    command.actor.id,
                )

        return Result[PaymentAuthorizationView].ok(
            PaymentAuthorizationView.from_domain(payment)
        )
