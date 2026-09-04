# ruff: noqa: E501
"""Команда и handler deactivate-product."""

import uuid
from dataclasses import dataclass

from kernel_domain.result import Result

from application.authorization import ProductAuthorizer
from application.errors import ProductNotFoundError
from application.ports import (
    Actor,
    IdentityGateway,
)
from contracts.product import ProductView
from domain.unit_of_work import CatalogUnitOfWork
from domain.value_objects.product_id import ProductId


@dataclass(frozen=True)
class DeactivateProductCommand:
    """DTO для команды деактивации товара."""

    product_id: uuid.UUID
    actor: Actor


class DeactivateProductCommandHandler:
    """
    Business Logic Summary

    Context & Purpose: Деактивация товара, скрытие его из общего каталога.
    Validations: Проверка прав (владелец или админ).
    Side Effects: Статус товара в репозитории меняется на неактивный.
    """

    def __init__(self, uow: CatalogUnitOfWork, identity: IdentityGateway) -> None:
        self._uow = uow
        self._authorizer = ProductAuthorizer(identity)

    async def execute(self, command: DeactivateProductCommand) -> Result[ProductView]:
        async with self._uow:
            product = await self._uow.products.get_by_id(
                ProductId.create(command.product_id)
            )
            if product is None:
                raise ProductNotFoundError
            await self._authorizer.require_owner_or_admin(command.actor, product)
            result = await self._uow.products.deactivate(product.id)
            if result is None:
                raise ProductNotFoundError
            if result.is_err:
                return Result[ProductView].fail(result.error)
            await self._uow.commit()
        return Result[ProductView].ok(ProductView.from_domain(result.value))
