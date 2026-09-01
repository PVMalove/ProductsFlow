"""Upsert-product-image command and handler."""

import uuid
from dataclasses import dataclass

from application._product_helpers import get_product
from application.authorization import ProductAuthorizer
from application.image_dto import ProductImageMutation, ProductImageView
from application.ports import (
    Actor,
    IdentityGateway,
    ProductCommandPort,
    ProductImageStorage,
    ProductQueryPort,
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
        self._query_repository: ProductQueryPort = repository  # type: ignore[assignment]
        self._authorizer = ProductAuthorizer(identity)
        self._storage = storage
        self._bucket_name = bucket_name

    async def handle(self, command: UpsertProductImageCommand) -> ProductImageMutation:
        product = await get_product(self._query_repository, command.product_id)
        await self._authorizer.require_owner_or_admin(command.actor, product)
        existing = await self._repository.get_product_image(product.id)
        key = IMAGE_KEY_TEMPLATE.format(product_id=product.id.value)

        await self._storage.put_object(
            self._bucket_name, key, command.body, command.content_type
        )
        image = await self._repository.upsert_product_image(
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
            view=ProductImageView(
                image_url=await self._storage.build_presigned_url(
                    self._bucket_name, image.s3_key
                ),
                updated_at=image.updated_at,
            ),
            replaced=existing is not None,
        )

    async def execute(
        self,
        product_id: uuid.UUID,
        *,
        actor: Actor,
        body: bytes,
        content_type: str,
    ) -> ProductImageMutation:
        return await self.handle(
            UpsertProductImageCommand(
                product_id=product_id,
                actor=actor,
                body=body,
                content_type=content_type,
            )
        )
