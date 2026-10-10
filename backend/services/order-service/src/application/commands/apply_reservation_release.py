# ruff: noqa: E501
"""Команда и handler применения факта `inventory.released.v1` (issue #375,
D6) — завершение компенсации Saga по прецеденту `apply_reservation_result.py`:
без UoW/`.commit()`, транзакцией управляет вызывающий адаптер
(`api/workers/commands/reservation_result_handler.py`)."""

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from domain.entities.order import Order
from domain.repositories import CartRepository, OrderRepository

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ApplyReservationReleaseCommand:
    order_id: uuid.UUID


class ApplyReservationReleaseCommandHandler:
    """
    Business Logic Summary

    Context & Purpose: Завершает компенсацию после отказа/таймаута авторизации — резерв освобождён, строки Order возвращаются в Cart (issue #375, ADR 0016:19).
    Validations: Order должен существовать (иначе no-op с warning); Order.complete_compensation — no-op вне COMPENSATING (повторная доставка; release в другом шаге — забота #377). Любой reason события (manual/expired) завершает компенсацию: резерв освобождён в обоих случаях.
    Side Effects: Order -> COMPENSATED (остаётся FAILED в истории со строками); Cart пользователя (get-or-create, под блокировкой строки) получает строки Order с причиной = failure_reason.
    """

    def __init__(self, order_repo: OrderRepository, cart_repo: CartRepository) -> None:
        self._order_repo = order_repo
        self._cart_repo = cart_repo

    async def execute(self, command: ApplyReservationReleaseCommand) -> None:
        order: Order | None = await self._order_repo.get_by_id(command.order_id)
        if order is None:
            logger.warning(
                "Reservation release проигнорирован: order_id=%s не найден",
                command.order_id,
            )
            return

        if not order.complete_compensation():
            logger.info(
                "Reservation release — no-op: order_id=%s не в COMPENSATING",
                command.order_id,
            )
            return

        await self._order_repo.save(order)

        assert order.failure_reason is not None, (
            "apply_authorization_result always sets a reason before COMPENSATING"
        )
        cart = await self._cart_repo.get_or_create_for_user(order.user_id)
        cart.return_order_lines(
            lines=order.lines, reason=order.failure_reason, now=datetime.now(UTC)
        )
        await self._cart_repo.save(cart)
