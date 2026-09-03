import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from kernel_domain.result import Result
from kernel_platform.http.envelope import ApiResponse
from kernel_platform.http.match import match_created, match_result
from kernel_platform.pagination import (
    DEFAULT_PAGE_LIMIT,
    MAX_PAGE_LIMIT,
    Cursor,
    InvalidCursorError,
    decode_cursor,
)

from api.dependencies import (
    ActivateProductDI,
    CreateProductDI,
    DeactivateProductDI,
    DeleteProductDI,
    GetProductAuditDI,
    GetProductDI,
    ListProductsDI,
    OptionalAuth,
    RequiredAuth,
    UpdateProductDI,
    to_actor,
)
from api.schemas import (
    ProductActivateRequest,
    ProductAuditLogResponse,
    ProductCreateRequest,
    ProductDeactivateRequest,
    ProductDeleteRequest,
    ProductGetRequest,
    ProductListResponse,
    ProductUpdateRequest,
)
from application.queries import (
    GetProductAuditQuery,
    ListProductsQuery,
)
from contracts.product import ProductView

router = APIRouter(prefix="/api/v1/products", tags=["products"])


@router.post(
    "",
    response_model=ApiResponse[ProductView],
    status_code=status.HTTP_201_CREATED,
)
async def create_product(
    request: ProductCreateRequest,
    auth: RequiredAuth,
    handler: CreateProductDI,
) -> ApiResponse[ProductView]:
    command = request.to_command(actor=to_actor(auth))
    result: Result[ProductView] = await handler.execute(command)
    return match_created(result)


@router.get("", response_model=ProductListResponse)
async def list_products(
    handler: ListProductsDI,
    limit: int = Query(default=DEFAULT_PAGE_LIMIT, ge=1, le=MAX_PAGE_LIMIT),
    after: str | None = Query(default=None),
    before: str | None = Query(default=None),
) -> ProductListResponse:
    if after is not None and before is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Нельзя одновременно указать after и before",
        )
    page = await handler.execute(
        ListProductsQuery(
            limit=limit,
            after=_parse_cursor(after),
            before=_parse_cursor(before),
        )
    )
    return ProductListResponse.from_domain(page)


@router.get("/{product_id}", response_model=ApiResponse[ProductView])
async def get_product(
    request: Annotated[ProductGetRequest, Depends()],
    auth: OptionalAuth,
    handler: GetProductDI,
) -> ApiResponse[ProductView]:
    query = request.to_query(actor=to_actor(auth) if auth is not None else None)
    result: Result[ProductView] = await handler.execute(query)
    return match_result(result)


@router.patch("/{product_id}", response_model=ApiResponse[ProductView])
async def update_product(
    product_id: uuid.UUID,
    request: ProductUpdateRequest,
    auth: RequiredAuth,
    handler: UpdateProductDI,
) -> ApiResponse[ProductView]:
    command = request.to_command(product_id=product_id, actor=to_actor(auth))
    result: Result[ProductView] = await handler.execute(command)
    return match_result(result)


@router.patch("/{product_id}/activate", response_model=ApiResponse[ProductView])
async def activate_product(
    request: Annotated[ProductActivateRequest, Depends()],
    auth: RequiredAuth,
    handler: ActivateProductDI,
) -> ApiResponse[ProductView]:
    command = request.to_command(actor=to_actor(auth))
    result: Result[ProductView] = await handler.execute(command)
    return match_result(result)


@router.patch("/{product_id}/deactivate", response_model=ApiResponse[ProductView])
async def deactivate_product(
    request: Annotated[ProductDeactivateRequest, Depends()],
    auth: RequiredAuth,
    handler: DeactivateProductDI,
) -> ApiResponse[ProductView]:
    command = request.to_command(actor=to_actor(auth))
    result: Result[ProductView] = await handler.execute(command)
    return match_result(result)


@router.delete("/{product_id}", response_model=ApiResponse[None])
async def delete_product(
    request: Annotated[ProductDeleteRequest, Depends()],
    auth: RequiredAuth,
    handler: DeleteProductDI,
) -> ApiResponse[None]:
    command = request.to_command(actor=to_actor(auth))
    result: Result[None] = await handler.execute(command)
    return match_result(result)


@router.get("/{product_id}/audit", response_model=list[ProductAuditLogResponse])
async def get_product_audit(
    product_id: uuid.UUID,
    auth: RequiredAuth,
    handler: GetProductAuditDI,
) -> list[ProductAuditLogResponse]:
    entries = await handler.execute(
        GetProductAuditQuery(product_id=product_id, actor=to_actor(auth))
    )
    return [ProductAuditLogResponse.from_entry(entry) for entry in entries]


def _parse_cursor(raw: str | None) -> Cursor | None:
    if raw is None:
        return None
    try:
        return decode_cursor(raw)
    except InvalidCursorError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Некорректный курсор пагинации",
        ) from exc
