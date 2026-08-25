from typing import Annotated

from fastapi import APIRouter, File, HTTPException, Response, UploadFile, status

from app.db import SEED_KEY_PREFIX
from app.repository import ProductRepositoryDI
from app.router.product_visibility import (
    ensure_owner_or_admin,
    ensure_product_exists,
    is_admin,
)
from app.schemas import ProductId, ProductImageResponse
from app.security import CurrentUser, OptionalUser
from app.settings import settings
from app.storage import StorageDI

router = APIRouter(prefix="/products", tags=["products"])

_NO_IMAGE_DETAIL = "У товара нет картинки!"
_ALLOWED_CONTENT_TYPES = frozenset({"image/jpeg", "image/png", "image/webp"})
_MAX_IMAGE_SIZE = 1024 * 1024 * 5


@router.get(
    "/{product_id}/image",
    response_model=ProductImageResponse,
)
async def get_product_image(
    product_id: ProductId,
    repository: ProductRepositoryDI,
    storage: StorageDI,
    viewer: OptionalUser,
) -> ProductImageResponse:
    ensure_product_exists(
        await repository.get_product_by_id(
            product_id,
            viewer_is_admin=is_admin(viewer),
            viewer_id=viewer.id if viewer is not None else None,
        )
    )
    image = await repository.get_product_image_by_id(product_id)
    if image is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=_NO_IMAGE_DETAIL,
        )
    return ProductImageResponse(
        image_url=storage.build_public_url(
            settings.minio_bucket_name_product,
            image.s3_key,
            int(image.updated_at.timestamp()),
        ),
        updated_at=image.updated_at,
    )


@router.post(
    "/{product_id}/image",
    response_model=ProductImageResponse,
)
async def upload_product_image(
    product_id: ProductId,
    repository: ProductRepositoryDI,
    storage: StorageDI,
    current_user: CurrentUser,
    response: Response,
    file: Annotated[UploadFile, File(description="JPEG/PNG/WEBP, до 5 МБ")],
) -> ProductImageResponse:
    if file.content_type not in _ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Допустимы только JPEG, PNG, WEBP форматы",
        )
    body = await file.read()
    if len(body) > _MAX_IMAGE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail="Файл больше 5 МБ",
        )

    existing_product = ensure_product_exists(
        await repository.get_product_by_id(product_id, viewer_is_admin=True)
    )
    ensure_owner_or_admin(existing_product, current_user)

    existing_image = await repository.get_product_image_by_id(product_id)
    new_key = f"products/{product_id}/image"

    await storage.put_object(
        settings.minio_bucket_name_product, new_key, body, file.content_type
    )
    image = await repository.upsert_product_image(
        product_id,
        s3_key=new_key,
        content_type=file.content_type,
        size_bytes=len(body),
        actor_user_id=current_user.id,
    )
    if (
        existing_image is not None
        and existing_image.s3_key != new_key
        and not existing_image.s3_key.startswith(SEED_KEY_PREFIX)
    ):
        await storage.delete_object(
            settings.minio_bucket_name_product, existing_image.s3_key
        )

    response.status_code = (
        status.HTTP_200_OK if existing_image is not None else status.HTTP_201_CREATED
    )
    return ProductImageResponse(
        image_url=storage.build_public_url(
            settings.minio_bucket_name_product,
            image.s3_key,
            int(image.updated_at.timestamp()),
        ),
        updated_at=image.updated_at,
    )


@router.delete(
    "/{product_id}/image",
    response_model=None,
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_product_image(
    product_id: ProductId,
    repository: ProductRepositoryDI,
    storage: StorageDI,
    current_user: CurrentUser,
) -> None:
    existing_product = ensure_product_exists(
        await repository.get_product_by_id(product_id, viewer_is_admin=True)
    )
    ensure_owner_or_admin(existing_product, current_user)

    existing_image = await repository.get_product_image_by_id(product_id)
    if existing_image is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=_NO_IMAGE_DETAIL,
        )

    await repository.delete_product_image(product_id, actor_user_id=current_user.id)
    if not existing_image.s3_key.startswith(SEED_KEY_PREFIX):
        await storage.delete_object(
            settings.minio_bucket_name_product, existing_image.s3_key
        )
