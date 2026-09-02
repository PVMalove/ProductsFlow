"""Deactivate-product command and handler."""

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
class DeactivateProductCommand:
    product_id: uuid.UUID
    actor: Actor


class DeactivateProductCommandHandler:
    def __init__(
        self, repository: ProductCommandPort, identity: IdentityGateway
    ) -> None:
        self._repository = repository
        self._authorizer = ProductAuthorizer(identity)

    async def handle(self, command: DeactivateProductCommand) -> Result[Product]:
        product = await self._repository.get_by_id(ProductId(command.product_id))
        if product is None:
            raise ProductNotFoundError
        await self._authorizer.require_owner_or_admin(command.actor, product)
        result = await self._repository.deactivate(product.id)
        if result is None:
            raise ProductNotFoundError
        return result
