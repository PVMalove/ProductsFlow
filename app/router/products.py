from typing import TypeVar

from fastapi import APIRouter, HTTPException, Query, status

from app.models import Product, User, UserRole
from app.pagination import (
    DEFAULT_PAGE_LIMIT,
    MAX_PAGE_LIMIT,
    Cursor,
    InvalidCursorError,
    decode_cursor,
)
from app.repository import ProductAuditLogRepositoryDI, ProductRepositoryDI
from app.schemas import (
    ProductAuditLogResponse,
    ProductCreate,
    ProductId,
    ProductListResponse,
    ProductResponse,
    ProductUpdate,
)
from app.security import AdminUser, CurrentUser, OptionalUser

T = TypeVar("T")

router = APIRouter(prefix="/products", tags=["products"])


@router.get(
    "/",
    response_model=ProductListResponse,
)
async def get_products(
    repository: ProductRepositoryDI,
    viewer: OptionalUser,
    limit: int = Query(default=DEFAULT_PAGE_LIMIT, ge=1, le=MAX_PAGE_LIMIT),
    after: str | None = Query(default=None),
    before: str | None = Query(default=None),
) -> ProductListResponse:
    after_cursor, before_cursor, viewer_is_admin = _resolve_page_request(
        viewer, after, before
    )
    return await repository.get_products_page(
        limit=limit,
        after=after_cursor,
        before=before_cursor,
        viewer_is_admin=viewer_is_admin,
    )


@router.get(
    "/search",
    response_model=ProductListResponse,
)
async def search_products(
    query: str,
    repository: ProductRepositoryDI,
    viewer: OptionalUser,
    limit: int = Query(default=DEFAULT_PAGE_LIMIT, ge=1, le=MAX_PAGE_LIMIT),
    after: str | None = Query(default=None),
    before: str | None = Query(default=None),
) -> ProductListResponse:
    after_cursor, before_cursor, viewer_is_admin = _resolve_page_request(
        viewer, after, before
    )
    return await repository.search_products_page(
        query,
        limit=limit,
        after=after_cursor,
        before=before_cursor,
        viewer_is_admin=viewer_is_admin,
    )


@router.get(
    "/price-range",
    response_model=ProductListResponse,
)
async def get_products_by_price_range(
    repository: ProductRepositoryDI,
    viewer: OptionalUser,
    min_price: float | None = Query(default=None, ge=0),
    max_price: float | None = Query(default=None, ge=0),
    limit: int = Query(default=DEFAULT_PAGE_LIMIT, ge=1, le=MAX_PAGE_LIMIT),
    after: str | None = Query(default=None),
    before: str | None = Query(default=None),
) -> ProductListResponse:
    after_cursor, before_cursor, viewer_is_admin = _resolve_page_request(
        viewer, after, before
    )
    return await repository.get_products_by_price_range_page(
        min_price,
        max_price,
        limit=limit,
        after=after_cursor,
        before=before_cursor,
        viewer_is_admin=viewer_is_admin,
    )


@router.get(
    "/audit",
    response_model=list[ProductAuditLogResponse],
)
async def list_all_product_audit_logs(
    _admin: AdminUser,
    repository: ProductAuditLogRepositoryDI,
) -> list[ProductAuditLogResponse]:
    return await repository.get_all_audit_logs()


@router.get(
    "/{product_id}",
    response_model=ProductResponse,
)
async def get_product(
    product_id: ProductId, repository: ProductRepositoryDI, viewer: OptionalUser
) -> ProductResponse:
    return _ensure_product_exists(
        await repository.get_product_by_id(
            product_id, viewer_is_admin=_is_admin(viewer)
        )
    )


@router.get(
    "/category/{category_name}",
    response_model=ProductListResponse,
)
async def get_products_by_category(
    category_name: str,
    repository: ProductRepositoryDI,
    viewer: OptionalUser,
    limit: int = Query(default=DEFAULT_PAGE_LIMIT, ge=1, le=MAX_PAGE_LIMIT),
    after: str | None = Query(default=None),
    before: str | None = Query(default=None),
) -> ProductListResponse:
    after_cursor, before_cursor, viewer_is_admin = _resolve_page_request(
        viewer, after, before
    )
    return await repository.get_products_by_category_page(
        category_name,
        limit=limit,
        after=after_cursor,
        before=before_cursor,
        viewer_is_admin=viewer_is_admin,
    )


@router.post(
    "/",
    response_model=ProductResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_product(
    request: ProductCreate,
    repository: ProductRepositoryDI,
    current_user: CurrentUser,
) -> ProductResponse:
    return await repository.create_product(request, current_user.id)


@router.put(
    "/{product_id}",
    response_model=None,
    status_code=status.HTTP_204_NO_CONTENT,
)
async def update_product(
    product_id: ProductId,
    product_update: ProductUpdate,
    repository: ProductRepositoryDI,
    current_user: CurrentUser,
) -> None:
    existing_product = _ensure_product_exists(
        await repository.get_product_by_id(product_id, viewer_is_admin=True)
    )
    _ensure_owner_or_admin(existing_product, current_user)
    await repository.update_product(product_id, product_update)


@router.delete(
    "/{product_id}",
    response_model=None,
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_product(
    product_id: ProductId,
    repository: ProductRepositoryDI,
    current_user: CurrentUser,
) -> None:
    existing_product = _ensure_product_exists(
        await repository.get_product_by_id(product_id, viewer_is_admin=True)
    )
    _ensure_owner_or_admin(existing_product, current_user)
    await repository.delete_product(product_id)


@router.patch(
    "/{product_id}/activate",
    response_model=ProductResponse,
)
async def activate_product(
    product_id: ProductId,
    repository: ProductRepositoryDI,
    current_user: CurrentUser,
) -> ProductResponse:
    existing_product = _ensure_product_exists(
        await repository.get_product_by_id(product_id, viewer_is_admin=True)
    )
    _ensure_owner_or_admin(existing_product, current_user)
    return _ensure_product_exists(await repository.set_active_product(product_id, True))


@router.patch(
    "/{product_id}/deactivate",
    response_model=ProductResponse,
)
async def deactivate_product(
    product_id: ProductId,
    repository: ProductRepositoryDI,
    current_user: CurrentUser,
) -> ProductResponse:
    existing_product = _ensure_product_exists(
        await repository.get_product_by_id(product_id, viewer_is_admin=True)
    )
    _ensure_owner_or_admin(existing_product, current_user)
    return _ensure_product_exists(
        await repository.set_active_product(product_id, False)
    )


@router.get(
    "/{product_id}/audit",
    response_model=list[ProductAuditLogResponse],
)
async def get_product_audit_logs(
    product_id: ProductId,
    repository: ProductRepositoryDI,
    audit_repository: ProductAuditLogRepositoryDI,
    current_user: CurrentUser,
) -> list[ProductAuditLogResponse]:
    product = await repository.get_product_by_id(product_id, viewer_is_admin=True)
    logs = await audit_repository.get_audit_logs_by_product(product_id)

    if product is not None:
        _ensure_owner_or_admin(product, current_user)
    elif logs:
        # Продукт удалён — владельца проверить уже не по чему, доступ только админу.
        if current_user.role != UserRole.ADMIN:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Нет прав на этот продукт!",
            )
    else:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Продукт не найден!",
        )

    return logs


def _ensure_product_exists(entity: T | None) -> T:
    if not entity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Продукт не найден!",
        )
    return entity


def _ensure_owner_or_admin(
    product: Product | ProductResponse, current_user: User
) -> None:
    is_owner = product.user_id == current_user.id
    is_admin = current_user.role == UserRole.ADMIN
    if not (is_owner or is_admin):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Нет прав на этот продукт!",
        )


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


def _resolve_page_request(
    viewer: User | None, after: str | None, before: str | None
) -> tuple[Cursor | None, Cursor | None, bool]:
    """Общая часть параметров пагинации/видимости product-list-эндпоинтов"""
    if after is not None and before is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Нельзя одновременно указать after и before",
        )
    return _parse_cursor(after), _parse_cursor(before), _is_admin(viewer)


def _is_admin(viewer: User | None) -> bool:
    return viewer is not None and viewer.role == UserRole.ADMIN
