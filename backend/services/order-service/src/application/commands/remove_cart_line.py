# ruff: noqa: E501
"""Команда и handler удаления строки корзины (issue #369)."""

import logging
import uuid
from dataclasses import dataclass

from kernel_domain.result import Result
from kernel_platform.security import Actor

from application.errors import CartAccessDeniedError, CartLineNotFoundError
from domain.unit_of_work import CartUnitOfWork

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RemoveCartLineCommand:
    actor: Actor
    line_id: uuid.UUID


class RemoveCartLineCommandHandler:
    """
    Business Logic Summary

    Context & Purpose: Удаление строки из корзины вызывающего.
    Validations: `line_id` должен существовать (404) и принадлежать вызывающему (403) — обе проверки ДО мутации домена (D5).
    Side Effects: Строка удаляется из корзины безвозвратно.
    """

    def __init__(self, uow: CartUnitOfWork) -> None:
        self._uow = uow

    async def execute(self, command: RemoveCartLineCommand) -> Result[None]:
        async with self._uow:
            cart = await self._uow.carts.get_line_owner(command.line_id)
            if cart is None:
                logger.warning(
                    "Удаление строки корзины отклонено: line_id=%s не найдена",
                    command.line_id,
                )
                raise CartLineNotFoundError
            if cart.user_id != command.actor.id:
                logger.warning(
                    "Удаление строки корзины отклонено: line_id=%s принадлежит другому пользователю",
                    command.line_id,
                )
                raise CartAccessDeniedError

            result = cart.remove_line(line_id=command.line_id)
            if result.is_err:
                return Result[None].fail(result.error)

            await self._uow.carts.save(cart)
            await self._uow.commit()

        return Result[None].ok(None)
