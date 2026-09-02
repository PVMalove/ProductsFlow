"""Delete-product command and handler."""

import uuid
from dataclasses import dataclass

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
class DeleteProductCommand:
    product_id: uuid.UUID
    actor: Actor


class DeleteProductCommandHandler:
    def __init__(
        self, repository: ProductCommandPort, identity: IdentityGateway
    ) -> None:
        self._repository = repository
        self._authorizer = ProductAuthorizer(identity)

    async def handle(self, command: DeleteProductCommand) -> Product:
        product = await self._repository.get_by_id(ProductId(command.product_id))
        if product is None:
            raise ProductNotFoundError
        await self._authorizer.require_owner_or_admin(command.actor, product)
        deleted = await self._repository.delete(product.id)
        if deleted is None:
            raise ProductNotFoundError
        return deleted
