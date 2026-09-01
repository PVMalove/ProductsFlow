"""Delete-product command and handler."""

import uuid
from dataclasses import dataclass

from application._product_helpers import get_product
from application.authorization import ProductAuthorizer
from application.errors import ProductNotFoundError
from application.ports import (
    Actor,
    IdentityGateway,
    ProductCommandPort,
    ProductQueryPort,
)
from domain.product import Product


@dataclass(frozen=True)
class DeleteProductCommand:
    product_id: uuid.UUID
    actor: Actor


class DeleteProductCommandHandler:
    def __init__(
        self, repository: ProductCommandPort, identity: IdentityGateway
    ) -> None:
        self._repository = repository
        self._query_repository: ProductQueryPort = repository  # type: ignore[assignment]
        self._authorizer = ProductAuthorizer(identity)

    async def handle(self, command: DeleteProductCommand) -> Product:
        product = await get_product(self._query_repository, command.product_id)
        await self._authorizer.require_owner_or_admin(command.actor, product)
        deleted = await self._repository.delete(product.id)
        if deleted is None:
            raise ProductNotFoundError
        return deleted

    async def execute(self, product_id: uuid.UUID, *, actor: Actor) -> Product:
        return await self.handle(
            DeleteProductCommand(product_id=product_id, actor=actor)
        )
