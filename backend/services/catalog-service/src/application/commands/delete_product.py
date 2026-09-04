# ruff: noqa: E501
"""Команда и handler delete-product."""

import uuid
from dataclasses import dataclass

from kernel_domain.result import Result

from application.authorization import ProductAuthorizer
from application.errors import ProductNotFoundError
from application.ports import (
    Actor,
    IdentityGateway,
)
from domain.unit_of_work import CatalogUnitOfWork
from domain.value_objects.product_id import ProductId


@dataclass(frozen=True)
class DeleteProductCommand:
    """DTO для команды удаления товара."""

    product_id: uuid.UUID
    actor: Actor


class DeleteProductCommandHandler:
    """
    Business Logic Summary

    Context & Purpose: Полное удаление товара из системы.
    Validations: Строгая проверка прав (владелец или админ).
    Side Effects: Товар удаляется из базы данных.
    """

    def __init__(self, uow: CatalogUnitOfWork, identity: IdentityGateway) -> None:
        self._uow = uow
        self._authorizer = ProductAuthorizer(identity)

    async def execute(self, command: DeleteProductCommand) -> Result[None]:
        async with self._uow:
            product = await self._uow.products.get_by_id(
                ProductId.create(command.product_id)
            )
            if product is None:
                raise ProductNotFoundError
            await self._authorizer.require_owner_or_admin(command.actor, product)
            deleted = await self._uow.products.delete(product.id)
            if deleted is None:
                raise ProductNotFoundError
            await self._uow.commit()
        return Result[None].ok(None)
