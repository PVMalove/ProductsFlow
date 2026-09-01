from typing import Annotated

from fastapi import APIRouter, File, HTTPException, Response, UploadFile, status

from application.product_image_use_cases import ProductImageMutation
from presentation.dependencies import (
    DeleteProductImageDI,
    GetProductImageDI,
    OptionalAuth,
    RequiredAuth,
    UpsertProductImageDI,
    to_actor,
)
from presentation.schemas import ProductImageResponse

router = APIRouter(prefix="/api/v1/products", tags=["product-images"])

_ALLOWED_CONTENT_TYPES = frozenset({"image/jpeg", "image/png", "image/webp"})
_MAX_IMAGE_SIZE = 5 * 1024 * 1024


@router.get("/{product_id}/image", response_model=ProductImageResponse)
async def get_product_image(
    product_id: int,
    auth: OptionalAuth,
    use_case: GetProductImageDI,
) -> ProductImageResponse:
    view = await use_case.execute(
        product_id, actor=to_actor(auth) if auth is not None else None
    )
    return ProductImageResponse.from_view(view)


@router.post("/{product_id}/image", response_model=ProductImageResponse)
async def upload_product_image(
    product_id: int,
    auth: RequiredAuth,
    use_case: UpsertProductImageDI,
    response: Response,
    file: Annotated[UploadFile, File(description="JPEG/PNG/WEBP, до 5 МБ")],
) -> ProductImageResponse:
    if file.content_type not in _ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Допустимы только JPEG, PNG, WEBP форматы",
        )
    body = await file.read(_MAX_IMAGE_SIZE + 1)
    if len(body) > _MAX_IMAGE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail="Файл больше 5 МБ",
        )

    mutation: ProductImageMutation = await use_case.execute(
        product_id,
        actor=to_actor(auth),
        body=body,
        content_type=file.content_type,
    )
    response.status_code = (
        status.HTTP_200_OK if mutation.replaced else status.HTTP_201_CREATED
    )
    return ProductImageResponse.from_view(mutation.view)


@router.delete("/{product_id}/image", status_code=status.HTTP_204_NO_CONTENT)
async def delete_product_image(
    product_id: int,
    auth: RequiredAuth,
    use_case: DeleteProductImageDI,
) -> None:
    await use_case.execute(product_id, actor=to_actor(auth))


__all__ = ["router"]
