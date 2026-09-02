# ruff: noqa: E501
"""Activate-product command and handler."""

import uuid
from dataclasses import dataclass

from kernel_domain.result import Result

from application.authorization import ProductAuthorizer
from application.errors import ProductNotFoundError
from application.ports import (
    Actor,
    IdentityGateway,
    ProductCommandPort,
)
from domain.product import Product
from domain.product_id import ProductId


@dataclass(frozen=True)
class ActivateProductCommand:
    """DTO для команды активации товара."""

    product_id: uuid.UUID
    actor: Actor


class ActivateProductCommandHandler:
    """
    Business Logic Summary

    Context & Purpose: Активация товара в каталоге, делая его доступным для покупателей.
    Validations: Проверка прав доступа через IdentityGateway (только владелец или админ).
    Side Effects: Обновляется статус товара в репозитории на активный.
    """

    def __init__(
        self, repository: ProductCommandPort, identity: IdentityGateway
    ) -> None:
        self._repository = repository
        self._authorizer = ProductAuthorizer(identity)

    async def execute(self, command: ActivateProductCommand) -> Result[Product]:
        product = await self._repository.get_by_id(ProductId(command.product_id))
        if product is None:
            raise ProductNotFoundError
        await self._authorizer.require_owner_or_admin(command.actor, product)
        result = await self._repository.activate(product.id)
        if result is None:
            raise ProductNotFoundError
        return result
