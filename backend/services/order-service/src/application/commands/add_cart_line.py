# ruff: noqa: E501
"""Команда и handler добавления строки в корзину (issue #369)."""

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from kernel_domain.result import Result
from kernel_platform.security import Actor

from contracts.cart import CartLineView
from domain.unit_of_work import CartUnitOfWork

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AddCartLineCommand:
    """DTO для добавления товара в корзину вызывающего. Get-or-create
    корзины и merge на повторном `product_id` — забота домена (D3/D4)."""

    actor: Actor
    product_id: uuid.UUID
    quantity: int


class AddCartLineCommandHandler:
    """
    Business Logic Summary

    Context & Purpose: Добавление товара в собственную корзину вызывающего; неявный get-or-create корзины (D3).
    Validations: Количество должно быть положительным целым (Cart.add_line).
    Side Effects: Повторное добавление того же product_id увеличивает quantity существующей строки, а не создаёт новую (D4).
    """

    def __init__(self, uow: CartUnitOfWork) -> None:
        self._uow = uow

    async def execute(self, command: AddCartLineCommand) -> Result[CartLineView]:
        async with self._uow:
            cart = await self._uow.carts.get_or_create_for_user(command.actor.id)
            result = cart.add_line(
                line_id=uuid.uuid4(),
                product_id=command.product_id,
                quantity=command.quantity,
                now=datetime.now(UTC),
            )
            if result.is_err:
                logger.warning(
                    "Добавление строки в корзину отклонено: user_id=%s code=%s",
                    command.actor.id,
                    result.error.code,
                )
                return Result[CartLineView].fail(result.error)

            await self._uow.carts.save(cart)
            await self._uow.commit()

        logger.info(
            "Строка добавлена в корзину: user_id=%s product_id=%s quantity=%s",
            command.actor.id,
            command.product_id,
            command.quantity,
        )
        return Result[CartLineView].ok(CartLineView.from_domain(result.value))
