"""Delete-product-image command and handler."""

import uuid
from dataclasses import dataclass

from application._product_helpers import get_product
from application.authorization import ProductAuthorizer
from application.commands.upsert_product_image import SEED_KEY_PREFIX
from application.errors import ProductImageNotFoundError
from application.ports import (
    Actor,
    IdentityGateway,
    ProductCommandPort,
    ProductImageStorage,
)


@dataclass(frozen=True)
class DeleteProductImageCommand:
    product_id: uuid.UUID
    actor: Actor


class DeleteProductImageCommandHandler:
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

    async def handle(self, command: DeleteProductImageCommand) -> None:
        product = await get_product(self._repository, command.product_id)
        await self._authorizer.require_owner_or_admin(command.actor, product)
        image = await self._repository.get_product_image(product.id)
        if image is None:
            raise ProductImageNotFoundError

        await self._repository.delete_product_image(
            product.id, actor_user_id=command.actor.user_id
        )
        if not image.s3_key.startswith(SEED_KEY_PREFIX):
            await self._storage.delete_object(self._bucket_name, image.s3_key)
