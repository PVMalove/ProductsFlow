# ruff: noqa: E501
"""Update-product command and handler."""

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
from domain.product_id import ProductId
from domain.unit_of_work import CatalogUnitOfWork


@dataclass(frozen=True)
class UpdateProductCommand:
    """DTO для команды обновления данных товара."""

    product_id: uuid.UUID
    actor: Actor
    name: str | None = None
    description: str | None = None
    price: float | None = None
    category: str | None = None


class UpdateProductCommandHandler:
    """
    Business Logic Summary

    Context & Purpose: Частичное или полное обновление полей товара (название, описание, цена, категория).
    Validations: Авторизация актора (владелец или админ).
    Side Effects: Обновляются соответствующие поля товара в базе.
    """

    def __init__(
        self, uow: CatalogUnitOfWork, identity: IdentityGateway
    ) -> None:
        self._uow = uow
        self._authorizer = ProductAuthorizer(identity)

    async def execute(self, command: UpdateProductCommand) -> Result[ProductView]:
        async with self._uow:
            product = await self._uow.products.get_by_id(ProductId(command.product_id))
            if product is None:
                raise ProductNotFoundError
            await self._authorizer.require_owner_or_admin(command.actor, product)
            result = await self._uow.products.update(
                product.id,
                name=command.name,
                description=command.description,
                price=command.price,
                category=command.category,
            )
            if result is None:
                raise ProductNotFoundError
            if result.is_err:
                return Result[ProductView].fail(result.error)
            await self._uow.commit()
        return Result[ProductView].ok(ProductView.from_domain(result.value))
