from typing import Annotated

from fastapi import APIRouter, Depends, File, Response, UploadFile, status
from kernel_domain.result import Result
from kernel_platform.http.envelope import ApiResponse
from kernel_platform.http.errors import ApiError, status_code_for_error_type
from kernel_platform.http.match import match_result

from api.dependencies import (
    DeleteProductImageDI,
    GetProductImageDI,
    OptionalAuth,
    RequiredAuth,
    UpsertProductImageDI,
    to_actor,
)
from api.schemas import (
    ProductImageDeleteRequest,
    ProductImageGetRequest,
    ProductImageUploadRequest,
)
from application.image_dto import ProductImageMutation, ProductImageView
from application.queries import GetProductImageQuery

router = APIRouter(prefix="/api/v1/products", tags=["product-images"])


def _unwrap[T](result: Result[T]) -> T:
    """The upload endpoint needs the mutation's `replaced` flag to pick a
    status code before it can build the response View — a shape
    `match_result`/`match_created` don't fit — so this keeps the same error
    translation without wrapping the success value."""
    if result.is_err:
        error = result.error
        raise ApiError(
            status_code=status_code_for_error_type(error.type),
            code=error.code,
            message=error.description,
        )
    return result.value


@router.get("/{product_id}/image", response_model=ApiResponse[ProductImageView])
async def get_product_image(
    request: Annotated[ProductImageGetRequest, Depends()],
    auth: OptionalAuth,
    handler: GetProductImageDI,
) -> ApiResponse[ProductImageView]:
    query = request.to_query(actor=to_actor(auth) if auth is not None else None)
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
    actor = to_actor(auth)
    command = await request.to_command(file=file, actor=actor)
    mutation: ProductImageMutation = _unwrap(await handler.execute(command))
    response.status_code = (
        status.HTTP_200_OK if mutation.replaced else status.HTTP_201_CREATED
    )
    # `ProductImageMutation` deliberately carries only `replaced` — command
    # handlers don't return query-side Views in this codebase (CQRS, see
    # `test_image_command_result_does_not_expose_a_query_view`) — so the
    # response View comes from a second, read-side handler call, not from
    # collapsing the two into one.
    view_result: Result[ProductImageView] = await read_handler.execute(
        GetProductImageQuery(product_id=request.product_id, actor=actor)
    )
    return match_result(view_result)


@router.delete("/{product_id}/image", response_model=ApiResponse[None])
async def delete_product_image(
    request: Annotated[ProductImageDeleteRequest, Depends()],
    auth: RequiredAuth,
    handler: DeleteProductImageDI,
) -> ApiResponse[None]:
    command = request.to_command(actor=to_actor(auth))
    result: Result[None] = await handler.execute(command)
    return match_result(result)


__all__ = ["router"]
