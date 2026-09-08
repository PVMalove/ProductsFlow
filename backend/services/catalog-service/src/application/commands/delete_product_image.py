# ruff: noqa: E501
"""Команда и handler delete-product-image."""

import logging
import uuid
from dataclasses import dataclass

from kernel_domain.result import Result

from application.authorization import ProductAuthorizer
from application.commands.upsert_product_image import SEED_KEY_PREFIX
from application.errors import ProductImageNotFoundError, ProductNotFoundError
from application.ports import (
    Actor,
    IdentityGateway,
    ProductImageStorage,
)
from domain.unit_of_work import CatalogUnitOfWork
from domain.value_objects.product_id import ProductId

logger = logging.getLogger(__name__)


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
        uow: CatalogUnitOfWork,
        identity: IdentityGateway,
        storage: ProductImageStorage,
        bucket_name: str,
    ) -> None:
        self._uow = uow
        self._authorizer = ProductAuthorizer(identity)
        self._storage = storage
        self._bucket_name = bucket_name

    async def execute(self, command: DeleteProductImageCommand) -> Result[None]:
        async with self._uow:
            product = await self._uow.products.get_by_id(
                ProductId.create(command.product_id)
            )
            if product is None:
                logger.warning(
                    "Удаление изображения отклонено: товар не найден product_id=%s",
                    command.product_id,
                )
                raise ProductNotFoundError
            await self._authorizer.require_owner_or_admin(command.actor, product)
            image = await self._uow.products.get_product_image(product.id)
            if image is None:
                logger.warning(
                    "Удаление изображения отклонено: изображение не найдено product_id=%s",
                    command.product_id,
                )
                raise ProductImageNotFoundError

            await self._uow.products.delete_product_image(
                product.id, actor_user_id=command.actor.user_id
            )
            if not image.s3_key.startswith(SEED_KEY_PREFIX):
                await self._storage.delete_object(self._bucket_name, image.s3_key)
            await self._uow.commit()
        logger.info(
            "Изображение товара удалено: product_id=%s actor=%s",
            command.product_id,
            command.actor.user_id,
        )
        return Result[None].ok(None)
