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

from application.saga_compensation import void_stored_authorization
from domain.entities.order import Order, ReleaseReason, ReservationReleaseOutcome
from domain.repositories import (
    CartRepository,
    OrderRepository,
    SagaCommandOutboxRepository,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ApplyReservationReleaseCommand:
    order_id: uuid.UUID
    # issue #377, D7: `expired` — резерв истёк, а не освобождён по команде
    # Saga (`manual`).
    reason: ReleaseReason


class ApplyReservationReleaseCommandHandler:
    """
    Business Logic Summary

    Context & Purpose: Завершает компенсацию после отказа/таймаута авторизации или отмены владельцем — резерв освобождён, строки Order возвращаются в Cart (issue #375, #377, ADR 0016:19); истечение резерва незавершённого Order делает его EXPIRED (issue #377).
    Validations: Order должен существовать (иначе no-op с warning). Переход решает Order.apply_reservation_release: в COMPENSATING любой reason (manual/expired) завершает компенсацию; иначе reason=expired истекает PENDING до запроса capture либо завершает отменённый в AWAITING_RESERVATION; всё остальное (повтор, терминал, AWAITING_CAPTURE, manual вне COMPENSATING) — no-op.
    Side Effects: Компенсация -> COMPENSATED (Order остаётся FAILED/CANCELLED в истории со строками), строки Order возвращаются в Cart (get-or-create, причина = failure_reason). Истечение после результата резерва -> EXPIRED (RESERVATION_EXPIRED) + COMPENSATED, intent payment.void.v1 для сохранённой авторизации и возврат строк в Cart. Истечение в AWAITING_RESERVATION (PENDING или CANCELLED) -> COMPENSATED без команд: строки ещё в Cart под блокировкой этого Order, их только разблокирует Cart.unlock_all; поздний inventory.reserved.v1 — no-op.
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

        outcome = order.apply_reservation_release(reason=command.reason)
        match outcome:
            case ReservationReleaseOutcome.IGNORED:
                logger.info(
                    "Reservation release — no-op: order_id=%s не в COMPENSATING и не "
                    "истекает (reason=%s)",
                    command.order_id,
                    command.reason.value,
                )
                return
            case ReservationReleaseOutcome.COMPENSATION_COMPLETED:
                await self._order_repo.save(order)
                await self._return_lines_to_cart(order)
            case ReservationReleaseOutcome.EXPIRED_LINES_TAKEN:
                await self._order_repo.save(order)
                await void_stored_authorization(order, self._outbox)
                await self._return_lines_to_cart(order)
            case ReservationReleaseOutcome.EXPIRED_LINES_LOCKED:
                await self._order_repo.save(order)
                await self._unlock_cart_lines(order)

        if outcome is not ReservationReleaseOutcome.COMPENSATION_COMPLETED:
            logger.info(
                "Reservation expired: order_id=%s status=%s -> %s",
                command.order_id,
                order.status.value,
                order.saga_step.value,
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

    async def _unlock_cart_lines(self, order: Order) -> None:
        # Строки ещё в Cart под блокировкой этого Order: результат резерва их
        # не забрал.
        cart = await self._cart_repo.get_locked_by_order(order.id)
        if cart is not None:
            cart.unlock_all(order_id=order.id)
            await self._cart_repo.save(cart)
