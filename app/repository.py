from math import ceil
from typing import Annotated

from fastapi import Depends
from sqlalchemy import Select, asc, desc, exists, func, or_, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import Session
from app.models import (
    Product,
    ProductAuditLog,
    ProductImage,
    User,
    UserAuditAction,
    UserAuditLog,
)
from app.pagination import Cursor, encode_cursor
from app.schemas import (
    PageInfo,
    ProductAuditLogPage,
    ProductAuditLogResponse,
    ProductAuditSortField,
    ProductCreate,
    ProductId,
    ProductImageRecord,
    ProductListResponse,
    ProductResponse,
    ProductUpdate,
    UserAuditLogResponse,
    UserResponse,
)

# Whitelist sort_by -> реальная колонка (#36): защищает от произвольных имён
# полей, попадающих в ORDER BY.
_AUDIT_SORT_COLUMNS = {
    "created_at": ProductAuditLog.created_at,
    "action": ProductAuditLog.action,
    "actor_user_id": ProductAuditLog.actor_user_id,
    "product_id": ProductAuditLog.product_id,
}


class ProductRepository:
    """Репозиторий для работы с таблицей products"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_products_page(
        self,
        limit: int,
        after: Cursor | None,
        before: Cursor | None,
        viewer_is_admin: bool,
    ) -> ProductListResponse:
        """Постраничный список продуктов, новые сначала"""
        base_stmt = select(Product)
        if not viewer_is_admin:
            base_stmt = base_stmt.join(User, Product.user_id == User.id).where(
                User.is_active.is_(True), Product.is_active.is_(True)
            )
        return await self._fetch_page(
            base_stmt, limit=limit, after=after, before=before
        )

    async def product_exists(self, product_id: ProductId) -> bool:
        stmt = select(exists().where(Product.id == product_id))
        return bool(await self.session.scalar(stmt))

    async def get_product_by_id(
        self,
        product_id: ProductId,
        viewer_is_admin: bool,
        viewer_id: int | None = None,
    ) -> ProductResponse | None:
        """Получаем продукт по ID (видимость — только при viewer_is_admin=False)"""
        stmt = select(Product).where(Product.id == product_id)
        if not viewer_is_admin:
            # Видимость деактивированных владельцев — ADR 0002/CONTEXT.md.
            # Видимость деактивированного товара — ADR 0003, с исключением
            # для владельца, которое есть только при прямом доступе по ID.
            stmt = stmt.join(User, Product.user_id == User.id).where(
                User.is_active.is_(True),
                or_(Product.is_active.is_(True), Product.user_id == viewer_id),
            )
        product = await self.session.scalar(stmt)
        return ProductResponse.model_validate(product) if product else None

    async def get_product_image_by_id(
        self, product_id: ProductId
    ) -> ProductImageRecord | None:
        """Картинка товара по id товара, без логики видимости — она уже
        проверена раньше, тем же способом, что и для прямого получения
        товара (ADR 0007)."""
        stmt = select(ProductImage).where(ProductImage.product_id == product_id)
        image = await self.session.scalar(stmt)
        return ProductImageRecord.model_validate(image) if image else None

    async def search_products_page(
        self,
        query: str,
        limit: int,
        after: Cursor | None,
        before: Cursor | None,
        viewer_is_admin: bool,
    ) -> ProductListResponse:
        """Постраничный поиск по имени/описанию (без учёта регистра), новые сначала"""
        needle = f"%{query}%"
        base_stmt = select(Product).where(
            or_(
                Product.name.ilike(needle),
                Product.description.ilike(needle),
            )
        )
        if not viewer_is_admin:
            base_stmt = base_stmt.join(User, Product.user_id == User.id).where(
                User.is_active.is_(True), Product.is_active.is_(True)
            )
        return await self._fetch_page(
            base_stmt, limit=limit, after=after, before=before
        )

    async def get_products_by_category_page(
        self,
        category_name: str,
        limit: int,
        after: Cursor | None,
        before: Cursor | None,
        viewer_is_admin: bool,
    ) -> ProductListResponse:
        """Постраничный список по категории (без учёта регистра), новые сначала"""
        base_stmt = select(Product).where(Product.category.ilike(category_name))
        if not viewer_is_admin:
            base_stmt = base_stmt.join(User, Product.user_id == User.id).where(
                User.is_active.is_(True), Product.is_active.is_(True)
            )
        return await self._fetch_page(
            base_stmt, limit=limit, after=after, before=before
        )

    async def get_products_by_price_range_page(
        self,
        min_price: float | None,
        max_price: float | None,
        limit: int,
        after: Cursor | None,
        before: Cursor | None,
        viewer_is_admin: bool,
    ) -> ProductListResponse:
        """Постраничный список продуктов в диапазоне цен, новые сначала"""
        base_stmt = select(Product).where(
            Product.price.between(
                func.coalesce(min_price, Product.price),
                func.coalesce(max_price, Product.price),
            )
        )
        if not viewer_is_admin:
            base_stmt = base_stmt.join(User, Product.user_id == User.id).where(
                User.is_active.is_(True), Product.is_active.is_(True)
            )
        return await self._fetch_page(
            base_stmt, limit=limit, after=after, before=before
        )

    async def create_product(
        self, request: ProductCreate, user_id: int
    ) -> ProductResponse:
        """Создаём продукт"""
        product = Product(**request.model_dump(), user_id=user_id)
        self.session.add(product)
        await self.session.commit()
        await self.session.refresh(product)
        return ProductResponse.model_validate(product)

    async def update_product(
        self,
        product_id: ProductId,
        request: ProductUpdate,
    ) -> ProductResponse | None:
        """Обновляем продукт; None, если продукт с таким id не найден"""
        product = await self.session.get(Product, product_id)
        if not product:
            return None
        for key, value in request.model_dump(exclude_unset=True).items():
            setattr(product, key, value)
        await self.session.commit()
        await self.session.refresh(product)
        return ProductResponse.model_validate(product)

    async def set_active_product(
        self, product_id: ProductId, active: bool
    ) -> ProductResponse | None:
        """Переключаем видимость продукта; None, если продукт с таким id не найден"""
        product = await self.session.get(Product, product_id)
        if product is None:
            return None
        product.is_active = active
        await self.session.commit()
        await self.session.refresh(product)
        return ProductResponse.model_validate(product)

    async def delete_product(self, product_id: ProductId) -> ProductResponse | None:
        """Удаляем продукт; None, если продукт с таким id не найден"""
        product = await self.session.get(Product, product_id)
        if not product:
            return None
        snapshot = ProductResponse.model_validate(product)
        await self.session.delete(product)
        await self.session.commit()
        return snapshot

    async def _overfetch(
        self, stmt: Select[tuple[Product]], limit: int
    ) -> tuple[list[Product], bool]:
        """Выполняет stmt с overfetch +1 (ADR 0001); True = за limit есть ещё строка"""
        rows = list((await self.session.scalars(stmt.limit(limit + 1))).all())
        return rows[:limit], len(rows) > limit

    async def _fetch_page(
        self,
        base_stmt: Select[tuple[Product]],
        limit: int,
        after: Cursor | None,
        before: Cursor | None,
    ) -> ProductListResponse:
        # Общий keyset-хелпер поверх base_stmt — переиспользуется для #16-18.
        if before is not None:
            stmt = base_stmt.where(
                tuple_(Product.created_at, Product.id) > (before.created_at, before.id)
            ).order_by(Product.created_at.asc(), Product.id.asc())
            page, has_prev = await self._overfetch(stmt, limit)
            page.reverse()
            # before передан ⇒ есть страница вперёд, к более старым (Relay-style).
            has_more = True
        else:
            stmt = base_stmt
            if after is not None:
                stmt = stmt.where(
                    tuple_(Product.created_at, Product.id)
                    < (after.created_at, after.id)
                )
            stmt = stmt.order_by(Product.created_at.desc(), Product.id.desc())
            page, has_more = await self._overfetch(stmt, limit)
            # Relay-style: курсор передан ⇒ предыдущая страница есть.
            has_prev = after is not None

        if not page:
            # Пустая страница: оба курсора и флага — контракт issue #14.
            return ProductListResponse(
                items=[],
                page_info=PageInfo(
                    next_cursor=None, prev_cursor=None, has_more=False, has_prev=False
                ),
            )

        return ProductListResponse(
            items=[ProductResponse.model_validate(row) for row in page],
            page_info=PageInfo(
                next_cursor=(
                    encode_cursor(page[-1].created_at, page[-1].id)
                    if has_more
                    else None
                ),
                prev_cursor=(
                    encode_cursor(page[0].created_at, page[0].id) if has_prev else None
                ),
                has_more=has_more,
                has_prev=has_prev,
            ),
        )


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_all_users(self) -> list[UserResponse]:
        result = await self.session.scalars(select(User))
        return [UserResponse.model_validate(row) for row in result.all()]

    async def get_user_by_id(self, user_id: int) -> User | None:
        return await self.session.scalar(select(User).where(User.id == user_id))

    async def get_user_by_name(self, name: str) -> User | None:
        return await self.session.scalar(select(User).where(User.username == name))

    async def set_active_user(self, user_id: int, active: bool) -> User | None:
        user = await self.get_user_by_id(user_id)
        if user is None:
            return None
        user.is_active = active
        await self.session.commit()
        await self.session.refresh(user)
        return user

    async def create(self, username: str, password_hash: str) -> User:
        user = User(
            username=username,
            password_hash=password_hash,
        )
        self.session.add(user)
        await self.session.commit()
        await self.session.refresh(user)
        return user

    async def update_user_password(
        self, user_id: int, new_password: str
    ) -> User | None:
        user = await self.get_user_by_id(user_id)
        if user is None:
            return None
        user.password_hash = new_password
        await self.session.commit()
        await self.session.refresh(user)
        return user


class UserAuditLogRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_all_audit_logs(self) -> list[UserAuditLogResponse]:
        # Глобальный админский фид — новые записи сначала, в отличие от
        # хронологического get_audit_logs_by_user ниже. id тут — tie-breaker
        # для совпадающих created_at внутри одной транзакции, см. #29.
        stmt = select(UserAuditLog).order_by(
            UserAuditLog.created_at.desc(), UserAuditLog.id.desc()
        )
        return await self._fetch_audit_logs(stmt)

    async def get_audit_logs_by_user(self, user_id: int) -> list[UserAuditLogResponse]:
        stmt = (
            select(UserAuditLog)
            .where(UserAuditLog.user_id == user_id)
            .order_by(UserAuditLog.created_at.asc(), UserAuditLog.id.asc())
        )
        return await self._fetch_audit_logs(stmt)

    async def add_audit_log(
        self,
        user_id: int,
        actor_user_id: int,
        action: UserAuditAction,
        description: str = "",
    ) -> UserAuditLog:
        log = UserAuditLog(
            user_id=user_id,
            actor_user_id=actor_user_id,
            action=action,
            description=description,
        )
        self.session.add(log)
        await self.session.flush()
        await self.session.refresh(log)
        return log

    async def _fetch_audit_logs(
        self, stmt: Select[tuple[UserAuditLog]]
    ) -> list[UserAuditLogResponse]:
        result = await self.session.scalars(stmt)
        return [UserAuditLogResponse.model_validate(row) for row in result.all()]


class ProductAuditLogRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_all_audit_logs_page(
        self,
        page_index: int,
        page_size: int,
        sort_by: ProductAuditSortField = "created_at",
        sort_desc: bool = True,
    ) -> ProductAuditLogPage:
        # Глобальный админский фид — новые записи сначала по умолчанию, в
        # отличие от хронологического get_audit_logs_by_product ниже. id
        # тут — tie-breaker для совпадающих значений sort_by (в т.ч.
        # created_at внутри одной транзакции, см. #29), в том же
        # направлении, что и sort_by, см. #36. Offset вместо cursor —
        # обоснование в ADR 0005.
        total = await self.session.scalar(
            select(func.count()).select_from(ProductAuditLog)
        )
        total = total or 0
        direction = desc if sort_desc else asc
        sort_column = _AUDIT_SORT_COLUMNS[sort_by]
        stmt = (
            select(ProductAuditLog)
            .order_by(direction(sort_column), direction(ProductAuditLog.id))
            .limit(page_size)
            .offset((page_index - 1) * page_size)
        )
        items = await self._fetch_audit_logs(stmt)
        return ProductAuditLogPage(
            items=items,
            page_index=page_index,
            page_size=page_size,
            total=total,
            total_pages=ceil(total / page_size) if total else 0,
        )

    async def get_audit_logs_by_product(
        self, product_id: int
    ) -> list[ProductAuditLogResponse]:
        stmt = (
            select(ProductAuditLog)
            .where(ProductAuditLog.product_id == product_id)
            .order_by(ProductAuditLog.created_at.asc(), ProductAuditLog.id.asc())
        )
        return await self._fetch_audit_logs(stmt)

    async def _fetch_audit_logs(
        self, stmt: Select[tuple[ProductAuditLog]]
    ) -> list[ProductAuditLogResponse]:
        result = await self.session.scalars(stmt)
        return [ProductAuditLogResponse.model_validate(row) for row in result.all()]


def get_product_repository(session: Session) -> ProductRepository:
    return ProductRepository(session)


def get_user_repository(session: Session) -> UserRepository:
    return UserRepository(session)


def get_user_audit_log_repository(session: Session) -> UserAuditLogRepository:
    return UserAuditLogRepository(session)


def get_product_audit_log_repository(session: Session) -> ProductAuditLogRepository:
    return ProductAuditLogRepository(session)


ProductRepositoryDI = Annotated[ProductRepository, Depends(get_product_repository)]
UserRepositoryDI = Annotated[UserRepository, Depends(get_user_repository)]
UserAuditLogRepositoryDI = Annotated[
    UserAuditLogRepository, Depends(get_user_audit_log_repository)
]
ProductAuditLogRepositoryDI = Annotated[
    ProductAuditLogRepository, Depends(get_product_audit_log_repository)
]
