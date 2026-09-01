"""Get-product query and visibility handler."""

import uuid
from dataclasses import dataclass

from application.authorization import ProductAuthorizer
from application.errors import ProductNotFoundError
from application.ports import (
    Actor,
    IdentityGateway,
    OwnerQueryPort,
    ProductQueryPort,
)
from domain.product import Product
from domain.product_id import ProductId
from domain.viewer import Viewer
from domain.visibility import ProductVisibilityPolicy


@dataclass(frozen=True)
class GetProductQuery:
    product_id: uuid.UUID
    actor: Actor | None


class GetProductQueryHandler:
    def __init__(
        self,
        repository: ProductQueryPort,
        owner_read_model: OwnerQueryPort,
        identity: IdentityGateway,
    ) -> None:
        self._repository = repository
        self._owner_read_model = owner_read_model
        self._authorizer = ProductAuthorizer(identity)
        self._visibility = ProductVisibilityPolicy()

    async def handle(self, query: GetProductQuery) -> Product:
        product = await self._repository.get_by_id(ProductId(query.product_id))
        if product is None:
            raise ProductNotFoundError

        if query.actor is not None and query.actor.user_id == product.user_id:
            return product

        owner = await self._owner_read_model.get(product.user_id)
        viewer = Viewer(
            user_id=query.actor.user_id if query.actor is not None else None,
            is_admin=False,
        )
        if (
            owner is not None
            and owner.is_active
            and self._visibility.is_visible(viewer, product)
        ):
            return product

        if query.actor is not None and await self._authorizer.is_admin(query.actor):
            return product
        raise ProductNotFoundError

    async def execute(self, product_id: uuid.UUID, *, actor: Actor | None) -> Product:
        return await self.handle(GetProductQuery(product_id=product_id, actor=actor))
