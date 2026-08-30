from fastapi import APIRouter, HTTPException, Query, status

from catalog.api.errors import to_http_exception
from catalog.api.schemas import (
    ProductAuditLogResponse,
    ProductCreateRequest,
    ProductListResponse,
    ProductResponse,
    ProductUpdateRequest,
)
from catalog.domain.product import Product
from catalog.domain.product_id import ProductId
from catalog.domain.viewer import Viewer
from catalog.domain.visibility import ProductVisibilityPolicy
from catalog.infrastructure.db.audit import get_audit_logs_by_product
from catalog.infrastructure.db.owner_read_model import (
    ensure_owner_read_model_seeded,
    get_owner_read_model,
)
from catalog.infrastructure.db.pagination import (
    DEFAULT_PAGE_LIMIT,
    MAX_PAGE_LIMIT,
    Cursor,
    InvalidCursorError,
    decode_cursor,
)
from catalog.infrastructure.db.product_repository import ProductRepository
from catalog.infrastructure.db.session import DbSessionDI
from catalog.infrastructure.security.auth import (
    IdentityGatewayDI,
    OptionalAuth,
    RequiredAuth,
    ensure_owner_or_admin,
    is_admin,
)

router = APIRouter(prefix="/api/v1/products", tags=["products"])

_visibility = ProductVisibilityPolicy()
_NOT_FOUND = HTTPException(
    status_code=status.HTTP_404_NOT_FOUND, detail="Товар не найден"
)


@router.post("", response_model=ProductResponse, status_code=status.HTTP_201_CREATED)
async def create_product(
    request: ProductCreateRequest,
    session: DbSessionDI,
    auth: RequiredAuth,
    identity: IdentityGatewayDI,
) -> ProductResponse:
    # Story 15 (ADR 0012/0019): холодный промах read-модели самого создателя
    # закрывается здесь, до того как видимость Товара станет вопросом для
    # других Наблюдателей.
    await ensure_owner_read_model_seeded(
        session, identity, user_id=auth.user_id, token=auth.token
    )
    result = await ProductRepository(session).create(
        name=request.name,
        description=request.description,
        price=request.price,
        category=request.category,
        user_id=auth.user_id,
    )
    if result.is_err:
        raise to_http_exception(result.error)
    return ProductResponse.from_domain(result.value)


@router.get("", response_model=ProductListResponse)
async def list_products(
    session: DbSessionDI,
    limit: int = Query(default=DEFAULT_PAGE_LIMIT, ge=1, le=MAX_PAGE_LIMIT),
    after: str | None = Query(default=None),
    before: str | None = Query(default=None),
) -> ProductListResponse:
    if after is not None and before is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Нельзя одновременно указать after и before",
        )
    page = await ProductRepository(session).list(
        limit=limit, after=_parse_cursor(after), before=_parse_cursor(before)
    )
    return ProductListResponse.from_domain(page)


@router.get("/{product_id}", response_model=ProductResponse)
async def get_product(
    product_id: int,
    session: DbSessionDI,
    auth: OptionalAuth,
    identity: IdentityGatewayDI,
) -> ProductResponse:
    product = await ProductRepository(session).get_by_id(ProductId(product_id))
    if product is None:
        raise _NOT_FOUND

    if auth is not None and auth.user_id == product.user_id:
        # Владелец видит своё независимо от is_active (story 6) — добор
        # read-модели здесь на пользу будущим Наблюдателям, не этому ответу.
        await ensure_owner_read_model_seeded(
            session, identity, user_id=auth.user_id, token=auth.token
        )
        return ProductResponse.from_domain(product)

    owner_row = await get_owner_read_model(session, product.user_id)
    viewer = Viewer(user_id=auth.user_id if auth is not None else None, is_admin=False)
    if (
        owner_row is not None
        and owner_row.is_active
        and _visibility.is_visible(viewer, product)
    ):
        return ProductResponse.from_domain(product)

    # Не видим по обычным правилам — единственный оставшийся шанс: admin
    # (ADR 0012 «доступ даётся ролью», синхронная сверка только здесь).
    if await is_admin(auth, identity):
        return ProductResponse.from_domain(product)

    raise _NOT_FOUND


@router.patch("/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
async def update_product(
    product_id: int,
    request: ProductUpdateRequest,
    session: DbSessionDI,
    auth: RequiredAuth,
    identity: IdentityGatewayDI,
) -> None:
    repo = ProductRepository(session)
    existing = await _get_or_404(repo, product_id)
    await ensure_owner_or_admin(auth, existing.user_id, identity)

    result = await repo.update(
        ProductId(product_id), **request.model_dump(exclude_unset=True)
    )
    if result is None:
        raise _NOT_FOUND
    if result.is_err:
        raise to_http_exception(result.error)


@router.patch("/{product_id}/activate", response_model=ProductResponse)
async def activate_product(
    product_id: int,
    session: DbSessionDI,
    auth: RequiredAuth,
    identity: IdentityGatewayDI,
) -> ProductResponse:
    repo = ProductRepository(session)
    existing = await _get_or_404(repo, product_id)
    await ensure_owner_or_admin(auth, existing.user_id, identity)

    result = await repo.activate(ProductId(product_id))
    if result is None:
        raise _NOT_FOUND
    if result.is_err:
        raise to_http_exception(result.error)
    return ProductResponse.from_domain(result.value)


@router.patch("/{product_id}/deactivate", response_model=ProductResponse)
async def deactivate_product(
    product_id: int,
    session: DbSessionDI,
    auth: RequiredAuth,
    identity: IdentityGatewayDI,
) -> ProductResponse:
    repo = ProductRepository(session)
    existing = await _get_or_404(repo, product_id)
    await ensure_owner_or_admin(auth, existing.user_id, identity)

    result = await repo.deactivate(ProductId(product_id))
    if result is None:
        raise _NOT_FOUND
    if result.is_err:
        raise to_http_exception(result.error)
    return ProductResponse.from_domain(result.value)


@router.delete("/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_product(
    product_id: int,
    session: DbSessionDI,
    auth: RequiredAuth,
    identity: IdentityGatewayDI,
) -> None:
    repo = ProductRepository(session)
    existing = await _get_or_404(repo, product_id)
    await ensure_owner_or_admin(auth, existing.user_id, identity)

    if await repo.delete(ProductId(product_id)) is None:
        raise _NOT_FOUND


@router.get("/{product_id}/audit", response_model=list[ProductAuditLogResponse])
async def get_product_audit(
    product_id: int,
    session: DbSessionDI,
    auth: RequiredAuth,
    identity: IdentityGatewayDI,
) -> list[ProductAuditLogResponse]:
    product = await ProductRepository(session).get_by_id(ProductId(product_id))
    logs = await get_audit_logs_by_product(session, product_id)

    if product is not None:
        await ensure_owner_or_admin(auth, product.user_id, identity)
    elif logs:
        # Товар удалён — владельца проверить уже не по чему (issue #149:
        # `product_audit_log` без FK/user_id, CONTEXT.md «Существование
        # продукта») — доступ только admin.
        if not await is_admin(auth, identity):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Нет прав на этот товар"
            )
    else:
        raise _NOT_FOUND

    return [ProductAuditLogResponse.from_row(row) for row in logs]


async def _get_or_404(repo: ProductRepository, product_id: int) -> Product:
    product = await repo.get_by_id(ProductId(product_id))
    if product is None:
        raise _NOT_FOUND
    return product


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
