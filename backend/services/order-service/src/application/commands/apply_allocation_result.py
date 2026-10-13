# ruff: noqa: E501
"""Команда и handler применения факта `inventory.allocated.v1` (issue #376,
D4) — message-driven use case по прецеденту `apply_reservation_result.py`:
без UoW/`.commit()`, транзакцией управляет вызывающий адаптер
(`api/workers/commands/inventory_event_handler.py`)."""

import logging
import uuid
from dataclasses import dataclass

from domain.entities.order import Order
from domain.repositories import OrderRepository, SagaCommandOutboxRepository

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ApplyAllocationResultCommand:
    order_id: uuid.UUID


class ApplyAllocationResultCommandHandler:
    """
    Business Logic Summary

    Context & Purpose: Продолжает Saga после успешной allocation резерва — только теперь Order запрашивает capture авторизованного платежа (issue #376, ADR 0016).
    Validations: Order должен существовать (иначе no-op с warning); Order.apply_allocation_result — no-op вне AWAITING_ALLOCATION (повторная доставка, результат не в своём шаге).
    Side Effects: Order -> AWAITING_CAPTURE (статус PENDING) и один intent payment.capture.v1 на сохранённый payment_authorization_id.
    """

    def __init__(
        self, order_repo: OrderRepository, outbox: SagaCommandOutboxRepository
    ) -> None:
        self._order_repo = order_repo
        self._outbox = outbox

    async def execute(self, command: ApplyAllocationResultCommand) -> None:
        order: Order | None = await self._order_repo.get_locked_by_id(command.order_id)
        if order is None:
            logger.warning(
                "Allocation result проигнорирован: order_id=%s не найден",
                command.order_id,
            )
            return

        if not order.apply_allocation_result():
            logger.info(
                "Allocation result — no-op: order_id=%s не в AWAITING_ALLOCATION",
                command.order_id,
            )
            return

        await self._order_repo.save(order)

        assert order.payment_authorization_id is not None, (
            "apply_authorization_result always stores the id before AWAITING_ALLOCATION"
        )
        await self._outbox.enqueue_capture(
            order_id=order.id, authorization_id=order.payment_authorization_id
        )
