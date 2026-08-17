from typing import Annotated, Tuple

from fastapi import Depends
from sqlalchemy import Select, exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import Session
from app.models import (
    Product,
    ProductAuditLog,
    User,
    UserAuditAction,
    UserAuditLog,
)
from app.schemas import (
    ProductAuditLogResponse,
    ProductCreate,
    ProductId,
    ProductResponse,
    ProductUpdate,
    UserAuditLogResponse,
    UserResponse,
)


class ProductRepository:
    """Репозиторий для работы с таблицей products"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_all_products(self) -> list[ProductResponse]:
        """Получаем все продукты"""
        return await self._fetch_products(select(Product))

    async def product_exists(self, product_id: ProductId) -> bool:
        stmt = select(exists().where(Product.id == product_id))
        return bool(await self.session.scalar(stmt))

    async def get_product_by_id(self, product_id: ProductId) -> ProductResponse | None:
        """Получаем продукт по ID"""
        product = await self.session.get(Product, product_id)
        return ProductResponse.model_validate(product) if product else None

    async def search_products(self, query: str) -> list[ProductResponse]:
        """Поиск по имени и описанию (без учёта регистра)"""
        needle = f"%{query}%"
        stmt: Select[Tuple[Product]] = select(Product).where(
            or_(
                Product.name.ilike(needle),
                Product.description.ilike(needle),
            )
        )
        return await self._fetch_products(stmt)

    async def get_products_by_category(
        self, category_name: str
    ) -> list[ProductResponse]:
        """Поиск по категории"""
        stmt: Select[Tuple[Product]] = select(Product).where(
            func.lower(Product.category) == category_name.casefold()
        )
        return await self._fetch_products(stmt)

    async def get_products_by_price_range(
        self, min_price: float | None, max_price: float | None
    ) -> list[ProductResponse]:
        """Диапазон цен (границы опциональны)"""
        stmt: Select[Tuple[Product]] = select(Product).where(
            Product.price.between(
                func.coalesce(min_price, Product.price),
                func.coalesce(max_price, Product.price),
            )
        )
        return await self._fetch_products(stmt)

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
        """Обновляем продукт (True, если обновление прошло)"""
        product = await self.session.get(Product, product_id)
        if not product:
            return None
        for key, value in request.model_dump(exclude_unset=True).items():
            setattr(product, key, value)
        await self.session.commit()
        await self.session.refresh(product)
        return ProductResponse.model_validate(product)

    async def delete_product(self, product_id: ProductId) -> ProductResponse | None:
        """Удаляем продукт (True, если удаление прошло)"""
        product = await self.session.get(Product, product_id)
        if not product:
            return None
        snapshot = ProductResponse.model_validate(product)
        await self.session.delete(product)
        await self.session.commit()
        return snapshot

    async def _fetch_products(
        self, stmt: Select[Tuple[Product]]
    ) -> list[ProductResponse]:
        result = await self.session.scalars(stmt)
        return [ProductResponse.model_validate(row) for row in result.all()]


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
        return await self._fetch_audit_logs(select(UserAuditLog))

    async def get_audit_logs_by_user(self, user_id: int) -> list[UserAuditLogResponse]:
        stmt = (
            select(UserAuditLog)
            .where(UserAuditLog.user_id == user_id)
            .order_by(UserAuditLog.created_at.desc())
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
        self, stmt: Select[Tuple[UserAuditLog]]
    ) -> list[UserAuditLogResponse]:
        result = await self.session.scalars(stmt)
        return [UserAuditLogResponse.model_validate(row) for row in result.all()]


class ProductAuditLogRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_all_audit_logs(self) -> list[ProductAuditLogResponse]:
        return await self._fetch_audit_logs(select(ProductAuditLog))

    async def get_audit_logs_by_product(
        self, product_id: int
    ) -> list[ProductAuditLogResponse]:
        stmt = (
            select(ProductAuditLog)
            .where(ProductAuditLog.product_id == product_id)
            .order_by(ProductAuditLog.created_at.desc())
        )
        return await self._fetch_audit_logs(stmt)

    async def _fetch_audit_logs(
        self, stmt: Select[Tuple[ProductAuditLog]]
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
