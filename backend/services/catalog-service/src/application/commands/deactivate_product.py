"""Deactivate-product command and handler."""

import uuid
from dataclasses import dataclass

from kernel_domain.result import Result

from application._product_helpers import get_product
from application.authorization import ProductAuthorizer
from application.errors import ProductNotFoundError
from application.ports import (
    Actor,
    IdentityGateway,
    ProductCommandPort,
)
from domain.product import Product


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
        product = await get_product(self._repository, command.product_id)
        await self._authorizer.require_owner_or_admin(command.actor, product)
        result = await self._repository.deactivate(product.id)
        if result is None:
            raise ProductNotFoundError
        return result
