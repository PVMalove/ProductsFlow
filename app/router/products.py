from typing import TypeVar

from fastapi import APIRouter, HTTPException, Query, status

from app.models import Product, User, UserRole
from app.repository import ProductAuditLogRepositoryDI, ProductRepositoryDI
from app.schemas import (
    ProductAuditLogResponse,
    ProductCreate,
    ProductId,
    ProductResponse,
    ProductUpdate,
)
from app.security import AdminUser, CurrentUser

T = TypeVar("T")

router = APIRouter(prefix="/products", tags=["products"])


@router.get(
    "/",
    response_model=list[ProductResponse],
)
async def get_products(repository: ProductRepositoryDI) -> list[ProductResponse]:
    return await repository.get_all_products()


@router.get(
    "/search",
    response_model=list[ProductResponse],
)
async def search_products(
    query: str,
    repository: ProductRepositoryDI,
    _current_user: CurrentUser,
) -> list[ProductResponse]:
    return await repository.search_products(query)


@router.get(
    "/price-range",
    response_model=list[ProductResponse],
)
async def get_products_by_price_range(
    repository: ProductRepositoryDI,
    _current_user: CurrentUser,
    min_price: float | None = Query(default=None, ge=0),
    max_price: float | None = Query(default=None, ge=0),
) -> list[ProductResponse]:
    return await repository.get_products_by_price_range(min_price, max_price)


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
    product_id: ProductId, repository: ProductRepositoryDI
) -> ProductResponse:
    return ensure_product_exists(await repository.get_product_by_id(product_id))


@router.get(
    "/category/{category_name}",
    response_model=list[ProductResponse],
)
async def get_products_by_category(
    category_name: str,
    repository: ProductRepositoryDI,
    _current_user: CurrentUser,
) -> list[ProductResponse]:
    return await repository.get_products_by_category(category_name)


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
    existing_product = ensure_product_exists(
        await repository.get_product_by_id(product_id)
    )
    ensure_owner_or_admin(existing_product, current_user)
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
    existing_product = ensure_product_exists(
        await repository.get_product_by_id(product_id)
    )
    ensure_owner_or_admin(existing_product, current_user)
    await repository.delete_product(product_id)


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
    product = await repository.get_product_by_id(product_id)
    logs = await audit_repository.get_audit_logs_by_product(product_id)

    if product is not None:
        ensure_owner_or_admin(product, current_user)
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


def ensure_product_exists(entity: T | None) -> T:
    if not entity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Продукт не найден!",
        )
    return entity


def ensure_owner_or_admin(
    product: Product | ProductResponse, current_user: User
) -> None:
    is_owner = product.user_id == current_user.id
    is_admin = current_user.role == UserRole.ADMIN
    if not (is_owner or is_admin):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Нет прав на этот продукт!",
        )
