from typing import Annotated

from fastapi import APIRouter, Depends, File, Response, UploadFile, status
from kernel_domain.result import Result
from kernel_platform.http.envelope import ApiResponse
from kernel_platform.http.match import match_result, unwrap_result

from api.http.dependencies import (
    DeleteProductImageDI,
    GetProductImageDI,
    OptionalAuth,
    RequiredAuth,
    UpsertProductImageDI,
    to_actor,
)
from api.http.schemas import (
    ProductImageDeleteRequest,
    ProductImageGetRequest,
    ProductImageUploadRequest,
)
from application.commands.delete_product_image import DeleteProductImageCommand
from application.commands.upsert_product_image import UpsertProductImageCommand
from application.image_dto import ProductImageMutation, ProductImageView
from application.ports import Actor
from application.queries.get_product_image import GetProductImageQuery

router = APIRouter(prefix="/api/v1/products", tags=["product-images"])


@router.get("/{product_id}/image", response_model=ApiResponse[ProductImageView])
async def get_product_image(
    request: Annotated[ProductImageGetRequest, Depends()],
    auth: OptionalAuth,
    handler: GetProductImageDI,
) -> ApiResponse[ProductImageView]:
    query: GetProductImageQuery = request.to_query(
        actor=to_actor(auth) if auth is not None else None
    )
    result: Result[ProductImageView] = await handler.execute(query)
    return match_result(result)


@router.post("/{product_id}/image", response_model=ApiResponse[ProductImageView])
async def upload_product_image(
    request: Annotated[ProductImageUploadRequest, Depends()],
    auth: RequiredAuth,
    handler: UpsertProductImageDI,
    read_handler: GetProductImageDI,
    response: Response,
    file: Annotated[UploadFile, File(description="JPEG/PNG/WEBP, до 5 МБ")],
) -> ApiResponse[ProductImageView]:
    actor: Actor = to_actor(auth)
    command: UpsertProductImageCommand = await request.to_command(
        file=file, actor=actor
    )
    mutation: ProductImageMutation = unwrap_result(await handler.execute(command))
    response.status_code = (
        status.HTTP_200_OK if mutation.replaced else status.HTTP_201_CREATED
    )
    # `ProductImageMutation` намеренно несёт только `replaced` — command
    # handlers не возвращают query-side View в этой кодовой базе (CQRS, см.
    # `test_image_command_result_does_not_expose_a_query_view`) — поэтому
    # ответный View приходит из второго, read-side вызова handler'а, а не из
    # слияния двух в один.
    view_result: Result[ProductImageView] = await read_handler.execute(
        request.to_query(actor=actor)
    )
    return match_result(view_result)


@router.delete("/{product_id}/image", response_model=ApiResponse[None])
async def delete_product_image(
    request: Annotated[ProductImageDeleteRequest, Depends()],
    auth: RequiredAuth,
    handler: DeleteProductImageDI,
) -> ApiResponse[None]:
    command: DeleteProductImageCommand = request.to_command(actor=to_actor(auth))
    result: Result[None] = await handler.execute(command)
    return match_result(result)


__all__: list[str] = ["router"]
