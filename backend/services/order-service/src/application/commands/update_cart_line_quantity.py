# ruff: noqa: E501
"""Команда и handler изменения количества строки корзины (issue #369)."""

import logging
import uuid
from dataclasses import dataclass

from kernel_domain.result import Result
from kernel_platform.security import Actor

from application.errors import CartAccessDeniedError, CartLineNotFoundError
from contracts.cart import CartLineView
from domain.unit_of_work import CartUnitOfWork

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class UpdateCartLineQuantityCommand:
    actor: Actor
    line_id: uuid.UUID
    quantity: int


class UpdateCartLineQuantityCommandHandler:
    """
    Business Logic Summary

    Context & Purpose: Изменение количества уже существующей строки корзины.
    Validations: `line_id` должен существовать (404) и принадлежать вызывающему (403) — обе проверки ДО мутации домена (D5); количество должно быть положительным целым (Cart.update_line_quantity).
    Side Effects: Нет — обновляет уже существующую строку.
    """

    def __init__(self, uow: CartUnitOfWork) -> None:
        self._uow = uow

    async def execute(
        self, command: UpdateCartLineQuantityCommand
    ) -> Result[CartLineView]:
        async with self._uow:
            cart = await self._uow.carts.get_line_owner(command.line_id)
            if cart is None:
                logger.warning(
                    "Изменение строки корзины отклонено: line_id=%s не найдена",
                    command.line_id,
                )
                raise CartLineNotFoundError
            if cart.user_id != command.actor.id:
                logger.warning(
                    "Изменение строки корзины отклонено: line_id=%s принадлежит другому пользователю",
                    command.line_id,
                )
                raise CartAccessDeniedError

            result = cart.update_line_quantity(
                line_id=command.line_id, quantity=command.quantity
            )
            if result.is_err:
                return Result[CartLineView].fail(result.error)

            await self._uow.carts.save(cart)
            await self._uow.commit()

        return Result[CartLineView].ok(CartLineView.from_domain(result.value))
