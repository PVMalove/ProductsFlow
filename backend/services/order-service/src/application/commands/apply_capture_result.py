# ruff: noqa: E501
"""Команда и handler применения факта `payment.captured.v1` (issue #376,
D4) — message-driven use case по прецеденту `apply_reservation_result.py`:
без UoW/`.commit()`, транзакцией управляет вызывающий адаптер
(`api/workers/commands/authorization_result_handler.py`)."""

import logging
import uuid
from dataclasses import dataclass

from domain.entities.order import Order
from domain.repositories import OrderRepository

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ApplyCaptureResultCommand:
    order_id: uuid.UUID
    # `authorization_id` захваченной авторизации — должен совпасть с
    # `Order.payment_authorization_id`.
    authorization_id: uuid.UUID
    # `causation_id` входящего `payment.captured.v1` — id команды
    # `payment.capture.v1` этого Order.
    causation_id: uuid.UUID


class ApplyCaptureResultCommandHandler:
    """
    Business Logic Summary

    Context & Purpose: Завершает успешную Saga checkout — подтверждённый capture делает Order COMPLETED и публикует order.completed.v1 (issue #376, ADR 0016).
    Validations: Order должен существовать (иначе no-op с warning); Order.apply_capture_result — no-op вне AWAITING_CAPTURE (повторная доставка, capture раньше allocation, результат после CAPTURED) и для authorization_id, отличного от сохранённого payment_authorization_id.
    Side Effects: Order -> COMPLETED + CAPTURED; OrderRepository.save в той же транзакции пишет строку журнала Saga и дренирует OrderCompleted в outbox_messages.
    """

    def __init__(self, order_repo: OrderRepository) -> None:
        self._order_repo = order_repo

    async def execute(self, command: ApplyCaptureResultCommand) -> None:
        order: Order | None = await self._order_repo.get_by_id(command.order_id)
        if order is None:
            logger.warning(
                "Capture result проигнорирован: order_id=%s не найден",
                command.order_id,
            )
            return

        if not order.apply_capture_result(
            authorization_id=command.authorization_id,
            causation_id=command.causation_id,
        ):
            logger.info(
                "Capture result — no-op: order_id=%s не в AWAITING_CAPTURE "
                "или authorization_id=%s не его авторизация",
                command.order_id,
                command.authorization_id,
            )
            return

        await self._order_repo.save(order)
