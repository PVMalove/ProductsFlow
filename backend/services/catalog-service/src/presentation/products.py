from fastapi import APIRouter, HTTPException, Query, status

from application.pagination import (
    DEFAULT_PAGE_LIMIT,
    MAX_PAGE_LIMIT,
    Cursor,
    InvalidCursorError,
    decode_cursor,
)
from presentation.dependencies import (
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
from presentation.errors import to_http_exception
from presentation.schemas import (
    ProductAuditLogResponse,
    ProductCreateRequest,
    ProductListResponse,
    ProductResponse,
    ProductUpdateRequest,
)

router = APIRouter(prefix="/api/v1/products", tags=["products"])


@router.post("", response_model=ProductResponse, status_code=status.HTTP_201_CREATED)
async def create_product(
    request: ProductCreateRequest,
    auth: RequiredAuth,
    use_case: CreateProductDI,
) -> ProductResponse:
    result = await use_case.execute(
        actor=to_actor(auth),
        name=request.name,
        description=request.description,
        price=request.price,
        category=request.category,
    )
    if result.is_err:
        raise to_http_exception(result.error)
    return ProductResponse.from_domain(result.value)


@router.get("", response_model=ProductListResponse)
async def list_products(
    use_case: ListProductsDI,
    limit: int = Query(default=DEFAULT_PAGE_LIMIT, ge=1, le=MAX_PAGE_LIMIT),
    after: str | None = Query(default=None),
    before: str | None = Query(default=None),
) -> ProductListResponse:
    if after is not None and before is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Нельзя одновременно указать after и before",
        )
    page = await use_case.execute(
        limit=limit,
        after=_parse_cursor(after),
        before=_parse_cursor(before),
    )
    return ProductListResponse.from_domain(page)


@router.get("/{product_id}", response_model=ProductResponse)
async def get_product(
    product_id: int,
    auth: OptionalAuth,
    use_case: GetProductDI,
) -> ProductResponse:
    product = await use_case.execute(
        product_id, actor=to_actor(auth) if auth is not None else None
    )
    return ProductResponse.from_domain(product)


@router.patch("/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
async def update_product(
    product_id: int,
    request: ProductUpdateRequest,
    auth: RequiredAuth,
    use_case: UpdateProductDI,
) -> None:
    result = await use_case.execute(
        product_id,
        actor=to_actor(auth),
        **request.model_dump(exclude_unset=True),
    )
    if result.is_err:
        raise to_http_exception(result.error)


@router.patch("/{product_id}/activate", response_model=ProductResponse)
async def activate_product(
    product_id: int,
    auth: RequiredAuth,
    use_case: ActivateProductDI,
) -> ProductResponse:
    result = await use_case.execute(product_id, actor=to_actor(auth))
    if result.is_err:
        raise to_http_exception(result.error)
    return ProductResponse.from_domain(result.value)


@router.patch("/{product_id}/deactivate", response_model=ProductResponse)
async def deactivate_product(
    product_id: int,
    auth: RequiredAuth,
    use_case: DeactivateProductDI,
) -> ProductResponse:
    result = await use_case.execute(product_id, actor=to_actor(auth))
    if result.is_err:
        raise to_http_exception(result.error)
    return ProductResponse.from_domain(result.value)


@router.delete("/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_product(
    product_id: int,
    auth: RequiredAuth,
    use_case: DeleteProductDI,
) -> None:
    await use_case.execute(product_id, actor=to_actor(auth))


@router.get("/{product_id}/audit", response_model=list[ProductAuditLogResponse])
async def get_product_audit(
    product_id: int,
    auth: RequiredAuth,
    use_case: GetProductAuditDI,
) -> list[ProductAuditLogResponse]:
    entries = await use_case.execute(product_id, actor=to_actor(auth))
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
