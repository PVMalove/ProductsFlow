import uuid
from typing import Annotated

from fastapi import APIRouter, File, HTTPException, Response, UploadFile, status
from kernel_platform.http.envelope import ApiResponse

from api.dependencies import (
    DeleteProductImageDI,
    GetProductImageDI,
    OptionalAuth,
    RequiredAuth,
    UpsertProductImageDI,
    to_actor,
)
from application.commands import (
    DeleteProductImageCommand,
    UpsertProductImageCommand,
)
from application.image_dto import ProductImageMutation, ProductImageView
from application.queries import GetProductImageQuery

router = APIRouter(prefix="/api/v1/products", tags=["product-images"])

_ALLOWED_CONTENT_TYPES = frozenset({"image/jpeg", "image/png", "image/webp"})
_MAX_IMAGE_SIZE = 5 * 1024 * 1024


@router.get("/{product_id}/image", response_model=ApiResponse[ProductImageView])
async def get_product_image(
    product_id: uuid.UUID,
    auth: OptionalAuth,
    handler: GetProductImageDI,
) -> ApiResponse[ProductImageView]:
    view = await handler.execute(
        GetProductImageQuery(
            product_id=product_id,
            actor=to_actor(auth) if auth is not None else None,
        )
    )
    return ApiResponse(data=view)


@router.post("/{product_id}/image", response_model=ApiResponse[ProductImageView])
async def upload_product_image(
    product_id: uuid.UUID,
    auth: RequiredAuth,
    handler: UpsertProductImageDI,
    read_handler: GetProductImageDI,
    response: Response,
    file: Annotated[UploadFile, File(description="JPEG/PNG/WEBP, до 5 МБ")],
) -> ApiResponse[ProductImageView]:
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

    mutation: ProductImageMutation = await handler.execute(
        UpsertProductImageCommand(
            product_id=product_id,
            actor=to_actor(auth),
            body=body,
            content_type=file.content_type,
        )
    )
    response.status_code = (
        status.HTTP_200_OK if mutation.replaced else status.HTTP_201_CREATED
    )
    # `ProductImageMutation` deliberately carries only `replaced` — command
    # handlers don't return query-side Views in this codebase (CQRS, see
    # `test_image_command_result_does_not_expose_a_query_view`) — so the
    # response View comes from a second, read-side handler call, not from
    # collapsing the two into one.
    view = await read_handler.execute(
        GetProductImageQuery(product_id=product_id, actor=to_actor(auth))
    )
    return ApiResponse(data=view)


@router.delete("/{product_id}/image", response_model=ApiResponse[None])
async def delete_product_image(
    product_id: uuid.UUID,
    auth: RequiredAuth,
    handler: DeleteProductImageDI,
) -> ApiResponse[None]:
    await handler.execute(
        DeleteProductImageCommand(product_id=product_id, actor=to_actor(auth))
    )
    return ApiResponse(data=None)


__all__ = ["router"]
