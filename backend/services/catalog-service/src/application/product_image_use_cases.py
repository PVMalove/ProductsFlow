import uuid
from dataclasses import dataclass
from datetime import datetime

from application.authorization import ProductAuthorizer
from application.errors import ApplicationError
from application.ports import (
    Actor,
    IdentityGateway,
    OwnerReadModel,
    ProductImageStorage,
)
from application.product_use_cases import GetProduct, _get_product
from domain.product_image import ProductImage
from domain.repositories import ProductRepository

SEED_KEY_PREFIX = "seed/"
IMAGE_KEY_TEMPLATE = "products/{product_id}/image"


class ProductImageNotFoundError(ApplicationError):
    """The product is visible, but has no image record."""


@dataclass(frozen=True)
class ProductImageView:
    image_url: str
    updated_at: datetime


@dataclass(frozen=True)
class ProductImageMutation:
    view: ProductImageView
    replaced: bool


class GetProductImage:
    def __init__(
        self,
        repository: ProductRepository,
        owner_read_model: OwnerReadModel,
        identity: IdentityGateway,
        storage: ProductImageStorage,
        bucket_name: str,
    ) -> None:
        self._repository = repository
        self._product_reader = GetProduct(repository, owner_read_model, identity)
        self._storage = storage
        self._bucket_name = bucket_name

    async def execute(
        self, product_id: uuid.UUID, *, actor: Actor | None
    ) -> ProductImageView:
        product = await self._product_reader.execute(product_id, actor=actor)
        image = await self._repository.get_product_image(product.id)
        if image is None:
            raise ProductImageNotFoundError
        return await _to_view(self._storage, self._bucket_name, image)


class UpsertProductImage:
    def __init__(
        self,
        repository: ProductRepository,
        identity: IdentityGateway,
        storage: ProductImageStorage,
        bucket_name: str,
    ) -> None:
        self._repository = repository
        self._authorizer = ProductAuthorizer(identity)
        self._storage = storage
        self._bucket_name = bucket_name

    async def execute(
        self,
        product_id: uuid.UUID,
        *,
        actor: Actor,
        body: bytes,
        content_type: str,
    ) -> ProductImageMutation:
        product = await _get_product(self._repository, product_id)
        await self._authorizer.require_owner_or_admin(actor, product)
        existing = await self._repository.get_product_image(product.id)
        key = IMAGE_KEY_TEMPLATE.format(product_id=product.id.value)

        await self._storage.put_object(self._bucket_name, key, body, content_type)
        image = await self._repository.upsert_product_image(
            product.id,
            s3_key=key,
            content_type=content_type,
            size_bytes=len(body),
            actor_user_id=actor.user_id,
        )
        if (
            existing is not None
            and existing.s3_key != key
            and not existing.s3_key.startswith(SEED_KEY_PREFIX)
        ):
            await self._storage.delete_object(self._bucket_name, existing.s3_key)

        return ProductImageMutation(
            view=await _to_view(self._storage, self._bucket_name, image),
            replaced=existing is not None,
        )


class DeleteProductImage:
    def __init__(
        self,
        repository: ProductRepository,
        identity: IdentityGateway,
        storage: ProductImageStorage,
        bucket_name: str,
    ) -> None:
        self._repository = repository
        self._authorizer = ProductAuthorizer(identity)
        self._storage = storage
        self._bucket_name = bucket_name

    async def execute(self, product_id: uuid.UUID, *, actor: Actor) -> None:
        product = await _get_product(self._repository, product_id)
        await self._authorizer.require_owner_or_admin(actor, product)
        image = await self._repository.get_product_image(product.id)
        if image is None:
            raise ProductImageNotFoundError

        await self._repository.delete_product_image(
            product.id, actor_user_id=actor.user_id
        )
        if not image.s3_key.startswith(SEED_KEY_PREFIX):
            await self._storage.delete_object(self._bucket_name, image.s3_key)


async def _to_view(
    storage: ProductImageStorage, bucket_name: str, image: ProductImage
) -> ProductImageView:
    return ProductImageView(
        image_url=await storage.build_presigned_url(bucket_name, image.s3_key),
        updated_at=image.updated_at,
    )


__all__ = [
    "DeleteProductImage",
    "GetProductImage",
    "IMAGE_KEY_TEMPLATE",
    "ProductImageMutation",
    "ProductImageNotFoundError",
    "ProductImageView",
    "SEED_KEY_PREFIX",
    "UpsertProductImage",
]
