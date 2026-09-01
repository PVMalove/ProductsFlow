"""Get-product-image query and handler."""

import uuid
from dataclasses import dataclass

from application.errors import ProductImageNotFoundError
from application.image_dto import ProductImageView
from application.ports import (
    Actor,
    IdentityGateway,
    OwnerQueryPort,
    ProductImageStorage,
    ProductQueryPort,
)
from application.queries.get_product import GetProductQuery, GetProductQueryHandler


@dataclass(frozen=True)
class GetProductImageQuery:
    product_id: uuid.UUID
    actor: Actor | None


class GetProductImageQueryHandler:
    def __init__(
        self,
        repository: ProductQueryPort,
        owner_read_model: OwnerQueryPort,
        identity: IdentityGateway,
        storage: ProductImageStorage,
        bucket_name: str,
    ) -> None:
        self._repository = repository
        self._product_reader = GetProductQueryHandler(
            repository, owner_read_model, identity
        )
        self._storage = storage
        self._bucket_name = bucket_name

    async def handle(self, query: GetProductImageQuery) -> ProductImageView:
        product = await self._product_reader.handle(
            GetProductQuery(product_id=query.product_id, actor=query.actor)
        )
        image = await self._repository.get_product_image(product.id)
        if image is None:
            raise ProductImageNotFoundError
        return ProductImageView(
            image_url=await self._storage.build_presigned_url(
                self._bucket_name, image.s3_key
            ),
            updated_at=image.updated_at,
        )

    async def execute(
        self, product_id: uuid.UUID, *, actor: Actor | None
    ) -> ProductImageView:
        return await self.handle(
            GetProductImageQuery(product_id=product_id, actor=actor)
        )
