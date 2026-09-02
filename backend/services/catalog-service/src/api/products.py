import uuid

from fastapi import APIRouter, HTTPException, Query, status
from kernel_domain.result import Result
from kernel_platform.http.envelope import ApiResponse
from kernel_platform.http.match import match_created
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
from api.errors import to_http_exception
from api.schemas import (
    ProductAuditLogResponse,
    ProductCreateRequest,
    ProductListResponse,
    ProductResponse,
    ProductUpdateRequest,
)
from application.commands import (
    ActivateProductCommand,
    DeactivateProductCommand,
    DeleteProductCommand,
    UpdateProductCommand,
)
from application.queries import (
    GetProductAuditQuery,
    GetProductQuery,
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


@router.get("/{product_id}", response_model=ProductResponse)
async def get_product(
    product_id: uuid.UUID,
    auth: OptionalAuth,
    handler: GetProductDI,
) -> ProductResponse:
    product = await handler.execute(
        GetProductQuery(
            product_id=product_id,
            actor=to_actor(auth) if auth is not None else None,
        )
    )
    return ProductResponse.from_domain(product)


@router.patch("/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
async def update_product(
    product_id: uuid.UUID,
    request: ProductUpdateRequest,
    auth: RequiredAuth,
    handler: UpdateProductDI,
) -> None:
    result = await handler.execute(
        UpdateProductCommand(
            product_id=product_id,
            actor=to_actor(auth),
            **request.model_dump(exclude_unset=True),
        )
    )
    if result.is_err:
        raise to_http_exception(result.error)


@router.patch("/{product_id}/activate", response_model=ProductResponse)
async def activate_product(
    product_id: uuid.UUID,
    auth: RequiredAuth,
    handler: ActivateProductDI,
) -> ProductResponse:
    result = await handler.execute(
        ActivateProductCommand(product_id=product_id, actor=to_actor(auth))
    )
    if result.is_err:
        raise to_http_exception(result.error)
    return ProductResponse.from_domain(result.value)


@router.patch("/{product_id}/deactivate", response_model=ProductResponse)
async def deactivate_product(
    product_id: uuid.UUID,
    auth: RequiredAuth,
    handler: DeactivateProductDI,
) -> ProductResponse:
    result = await handler.execute(
        DeactivateProductCommand(product_id=product_id, actor=to_actor(auth))
    )
    if result.is_err:
        raise to_http_exception(result.error)
    return ProductResponse.from_domain(result.value)


@router.delete("/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_product(
    product_id: uuid.UUID,
    auth: RequiredAuth,
    handler: DeleteProductDI,
) -> None:
    await handler.execute(
        DeleteProductCommand(product_id=product_id, actor=to_actor(auth))
    )


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
