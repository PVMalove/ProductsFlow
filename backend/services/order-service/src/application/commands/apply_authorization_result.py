# ruff: noqa: E501
"""Команда и handler применения результата `payment.authorize.v1` (issue
#375, D6) — message-driven use case по прецеденту
`apply_reservation_result.py`: без UoW/`.commit()`, транзакцией управляет
вызывающий адаптер (`api/workers/commands/authorization_result_handler.py`)."""

import logging
import uuid
from dataclasses import dataclass

from domain.entities.order import AuthorizationOutcome, Order
from domain.repositories import OrderRepository, ReservationOutboxRepository

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ApplyAuthorizationResultCommand:
    order_id: uuid.UUID
    authorization_id: uuid.UUID
    outcome: AuthorizationOutcome


class ApplyAuthorizationResultCommandHandler:
    """
    Business Logic Summary

    Context & Purpose: Отражает результат авторизации платежа в Order — успех продолжает Saga к allocation, отказ/таймаут делает Order компенсируемым терминалом (issue #375).
    Validations: Order должен существовать (иначе no-op с warning); Order.apply_authorization_result несёт saga_step no-op guard против повторной доставки.
    Side Effects: Успех -> payment_authorization_id сохранён, AWAITING_ALLOCATION; отказ/таймаут -> FAILED + COMPENSATING и intent inventory.release.v1. Void не отправляется: отклонённую или неизвестную авторизацию payment-service не аннулирует.
    """

    def __init__(
        self, order_repo: OrderRepository, outbox: ReservationOutboxRepository
    ) -> None:
        self._order_repo = order_repo
        self._outbox = outbox

    async def execute(self, command: ApplyAuthorizationResultCommand) -> None:
        order: Order | None = await self._order_repo.get_by_id(command.order_id)
        if order is None:
            logger.warning(
                "Authorization result проигнорирован: order_id=%s не найден",
                command.order_id,
            )
            return

        applied = order.apply_authorization_result(
            outcome=command.outcome, authorization_id=command.authorization_id
        )
        if not applied:
            logger.info(
                "Authorization result — no-op: order_id=%s уже покинул "
                "AWAITING_AUTHORIZATION",
                command.order_id,
            )
            return

        await self._order_repo.save(order)

        if command.outcome is not AuthorizationOutcome.AUTHORIZED:
            await self._outbox.enqueue_release(order_id=command.order_id)
