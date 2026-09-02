"""Upsert-product-image command and handler."""

import uuid
from dataclasses import dataclass

from application._product_helpers import get_product
from application.authorization import ProductAuthorizer
from application.image_dto import ProductImageMutation
from application.ports import (
    Actor,
    IdentityGateway,
    ProductCommandPort,
    ProductImageStorage,
)

SEED_KEY_PREFIX = "seed/"
IMAGE_KEY_TEMPLATE = "products/{product_id}/image"


@dataclass(frozen=True)
class UpsertProductImageCommand:
    product_id: uuid.UUID
    actor: Actor
    body: bytes
    content_type: str


class UpsertProductImageCommandHandler:
    def __init__(
        self,
        repository: ProductCommandPort,
        identity: IdentityGateway,
        storage: ProductImageStorage,
        bucket_name: str,
    ) -> None:
        self._repository = repository
        self._authorizer = ProductAuthorizer(identity)
        self._storage = storage
        self._bucket_name = bucket_name

    async def handle(self, command: UpsertProductImageCommand) -> ProductImageMutation:
        product = await get_product(self._repository, command.product_id)
        await self._authorizer.require_owner_or_admin(command.actor, product)
        existing = await self._repository.get_product_image(product.id)
        key = IMAGE_KEY_TEMPLATE.format(product_id=product.id.value)

        await self._storage.put_object(
            self._bucket_name, key, command.body, command.content_type
        )
        await self._repository.upsert_product_image(
            product.id,
            s3_key=key,
            content_type=command.content_type,
            size_bytes=len(command.body),
            actor_user_id=command.actor.user_id,
        )
        if (
            existing is not None
            and existing.s3_key != key
            and not existing.s3_key.startswith(SEED_KEY_PREFIX)
        ):
            await self._storage.delete_object(self._bucket_name, existing.s3_key)

        return ProductImageMutation(
            replaced=existing is not None,
        )
