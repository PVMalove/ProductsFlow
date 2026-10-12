# ruff: noqa: E501
"""Команда и handler применения факта `inventory.released.v1` (issue #375,
D6) — завершение компенсации Saga по прецеденту `apply_reservation_result.py`:
без UoW/`.commit()`, транзакцией управляет вызывающий адаптер
(`api/workers/commands/inventory_event_handler.py`). issue #377, D4: истечение
резерва (`reason=expired`) у незавершённого Order — терминал `EXPIRED` с
void сохранённой авторизации и возвратом строк в той же транзакции."""

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from domain.entities.order import Order, OrderSagaStep
from domain.repositories import (
    CartRepository,
    OrderRepository,
    SagaCommandOutboxRepository,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ApplyReservationReleaseCommand:
    order_id: uuid.UUID
    # issue #377, D7: `reason=expired` — резерв истёк, а не освобождён по
    # команде Saga (`manual`).
    expired: bool


class ApplyReservationReleaseCommandHandler:
    """
    Business Logic Summary

    Context & Purpose: Завершает компенсацию после отказа/таймаута авторизации или отмены владельцем — резерв освобождён, строки Order возвращаются в Cart (issue #375, #377, ADR 0016:19); истечение резерва незавершённого Order делает его EXPIRED (issue #377).
    Validations: Order должен существовать (иначе no-op с warning). В COMPENSATING любой reason события (manual/expired) завершает компенсацию: резерв освобождён в обоих случаях. Иначе reason=expired применяет Order.expire — no-op вне PENDING до запроса capture (повтор, терминал, AWAITING_CAPTURE); reason=manual вне COMPENSATING — no-op.
    Side Effects: Компенсация -> COMPENSATED (Order остаётся FAILED/CANCELLED в истории со строками). Истечение -> EXPIRED (RESERVATION_EXPIRED) + COMPENSATED и intent payment.void.v1 для сохранённой авторизации; в AWAITING_RESERVATION шаг сохраняется до результата резерва. В обоих случаях при COMPENSATED Cart пользователя (get-or-create, под блокировкой строки) получает строки Order с причиной = failure_reason.
    """

    def __init__(
        self,
        order_repo: OrderRepository,
        cart_repo: CartRepository,
        outbox: SagaCommandOutboxRepository,
    ) -> None:
        self._order_repo = order_repo
        self._cart_repo = cart_repo
        self._outbox = outbox

    async def execute(self, command: ApplyReservationReleaseCommand) -> None:
        order: Order | None = await self._order_repo.get_locked_by_id(command.order_id)
        if order is None:
            logger.warning(
                "Reservation release проигнорирован: order_id=%s не найден",
                command.order_id,
            )
            return

        if order.complete_compensation():
            await self._order_repo.save(order)
            await self._return_lines_to_cart(order)
            return

        if command.expired and order.expire():
            await self._order_repo.save(order)
            if order.payment_authorization_id is not None:
                await self._outbox.enqueue_void(
                    order_id=order.id,
                    authorization_id=order.payment_authorization_id,
                )
            if order.saga_step is OrderSagaStep.COMPENSATED:
                await self._return_lines_to_cart(order)
            logger.info(
                "Reservation expired: order_id=%s -> EXPIRED (saga_step=%s)",
                command.order_id,
                order.saga_step.value,
            )
            return

        logger.info(
            "Reservation release — no-op: order_id=%s не в COMPENSATING и не "
            "истекает (expired=%s)",
            command.order_id,
            command.expired,
        )

    async def _return_lines_to_cart(self, order: Order) -> None:
        assert order.failure_reason is not None, (
            "every terminal compensation sets a reason (failure, cancel or expiry)"
        )
        cart = await self._cart_repo.get_or_create_for_user(order.user_id)
        cart.return_order_lines(
            lines=order.lines, reason=order.failure_reason, now=datetime.now(UTC)
        )
        await self._cart_repo.save(cart)
