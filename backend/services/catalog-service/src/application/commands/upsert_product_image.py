# ruff: noqa: E501
"""Upsert-product-image command and handler."""

import uuid
from dataclasses import dataclass

from kernel_domain.result import Result

from application.authorization import ProductAuthorizer
from application.errors import ProductNotFoundError
from application.image_dto import ProductImageMutation
from application.ports import (
    Actor,
    IdentityGateway,
    ProductImageStorage,
)
from domain.unit_of_work import CatalogUnitOfWork
from domain.value_objects.product_id import ProductId

SEED_KEY_PREFIX = "seed/"
IMAGE_KEY_TEMPLATE = "products/{product_id}/image"


@dataclass(frozen=True)
class UpsertProductImageCommand:
    """DTO для команды добавления или обновления изображения товара."""

    product_id: uuid.UUID
    actor: Actor
    body: bytes
    content_type: str


class UpsertProductImageCommandHandler:
    """
    Business Logic Summary

    Context & Purpose: Загрузка нового или замена старого изображения для товара.
    Validations: Проверка прав, проверка формата и размера изображения.
    Side Effects: Данные о новом изображении сохраняются в репозитории.
    """

    def __init__(
        self,
        uow: CatalogUnitOfWork,
        identity: IdentityGateway,
        storage: ProductImageStorage,
        bucket_name: str,
    ) -> None:
        self._uow = uow
        self._authorizer = ProductAuthorizer(identity)
        self._storage = storage
        self._bucket_name = bucket_name

    async def execute(
        self, command: UpsertProductImageCommand
    ) -> Result[ProductImageMutation]:
        async with self._uow:
            product = await self._uow.products.get_by_id(
                ProductId.create(command.product_id)
            )
            if product is None:
                raise ProductNotFoundError
            await self._authorizer.require_owner_or_admin(command.actor, product)
            existing = await self._uow.products.get_product_image(product.id)
            key = IMAGE_KEY_TEMPLATE.format(product_id=product.id.value)

            await self._storage.put_object(
                self._bucket_name, key, command.body, command.content_type
            )
            await self._uow.products.upsert_product_image(
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
            await self._uow.commit()

        return Result[ProductImageMutation].ok(
            ProductImageMutation(replaced=existing is not None)
        )
