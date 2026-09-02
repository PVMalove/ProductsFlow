# ruff: noqa: E501
"""Delete-product-image command and handler."""

import uuid
from dataclasses import dataclass

from application.authorization import ProductAuthorizer
from application.commands.upsert_product_image import SEED_KEY_PREFIX
from application.errors import ProductImageNotFoundError, ProductNotFoundError
from application.ports import (
    Actor,
    IdentityGateway,
    ProductCommandPort,
    ProductImageStorage,
)
from domain.product_id import ProductId


@dataclass(frozen=True)
class DeleteProductImageCommand:
    """DTO для команды удаления изображения товара."""

    product_id: uuid.UUID
    actor: Actor


class DeleteProductImageCommandHandler:
    """
    Business Logic Summary

    Context & Purpose: Удаление привязанного к товару изображения.
    Validations: Проверка прав доступа через Authorizer.
    Side Effects: Изображение удаляется из хранилища и репозитория.
    """

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

    async def execute(self, command: DeleteProductImageCommand) -> None:
        product = await self._repository.get_by_id(ProductId(command.product_id))
        if product is None:
            raise ProductNotFoundError
        await self._authorizer.require_owner_or_admin(command.actor, product)
        image = await self._repository.get_product_image(product.id)
        if image is None:
            raise ProductImageNotFoundError

        await self._repository.delete_product_image(
            product.id, actor_user_id=command.actor.user_id
        )
        if not image.s3_key.startswith(SEED_KEY_PREFIX):
            await self._storage.delete_object(self._bucket_name, image.s3_key)
