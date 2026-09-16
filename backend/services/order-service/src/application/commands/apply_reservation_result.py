# ruff: noqa: E501
"""Команда и handler применения факта `inventory.reserved.v1` (issue #372,
D7) — message-driven use case, мирует inventory's
`ReserveInventoryLinesCommandHandler` (issue #370, D8): чистая функция
`(order_repo, cart_repo) -> execute(...)`, без UoW/`.commit()` — транзакцией
управляет вызывающий адаптер (`api/reservation_result_handler.py`)."""

import logging
import uuid
from dataclasses import dataclass

from domain.entities.cart import Cart
from domain.entities.order import Order
from domain.repositories import CartRepository, OrderRepository

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ApplyReservationResultCommand:
    order_id: uuid.UUID
    confirmed_product_ids: frozenset[uuid.UUID]


class ApplyReservationResultCommandHandler:
    """
    Business Logic Summary

    Context & Purpose: Отражает результат async reservation round-trip в Order/Cart — единственная точка, где Saga #372 достигает терминала (зачастую промежуточного, см. D4).
    Validations: Order должен существовать (иначе no-op с warning); Order.apply_reservation_result уже несёт собственный saga_step no-op guard против повторной доставки (D7).
    Side Effects: Нулевой confirmed -> Cart.unlock_all (строки не меняются); частичный/полный confirmed -> Order.lines усечён, Cart.resolve_partial_reservation (confirmed строки удаляются, недоступные разблокируются с причиной).
    """

    def __init__(self, order_repo: OrderRepository, cart_repo: CartRepository) -> None:
        self._order_repo = order_repo
        self._cart_repo = cart_repo

    async def execute(self, command: ApplyReservationResultCommand) -> None:
        order: Order | None = await self._order_repo.get_by_id(command.order_id)
        if order is None:
            logger.warning(
                "Reservation result проигнорирован: order_id=%s не найден",
                command.order_id,
            )
            return

        applied = order.apply_reservation_result(
            confirmed_product_ids=command.confirmed_product_ids
        )
        if not applied:
            logger.info(
                "Reservation result — no-op: order_id=%s уже покинул "
                "AWAITING_RESERVATION",
                command.order_id,
            )
            return

        await self._order_repo.save(order)

        cart: Cart | None = await self._cart_repo.get_locked_by_order(command.order_id)
        if cart is None:
            logger.warning(
                "Reservation result: order_id=%s не заблокировал ни одной "
                "строки Cart (уже разблокирована/удалена?)",
                command.order_id,
            )
            return

        if command.confirmed_product_ids:
            cart.resolve_partial_reservation(
                order_id=command.order_id,
                confirmed_product_ids=command.confirmed_product_ids,
            )
        else:
            cart.unlock_all(order_id=command.order_id)
        await self._cart_repo.save(cart)
