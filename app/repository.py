from typing import Annotated, Tuple

from fastapi import Depends
from sqlalchemy import Select, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import Session
from app.models import Product, User
from app.schemas import (
    ProductCreate,
    ProductID,
    ProductResponse,
    ProductUpdate,
    UserResponse,
    UserCreate,
)


class ProductRepository:
    """Репозиторий для работы с таблицей products"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_all_products(self) -> list[ProductResponse]:
        """Получаем все продукты"""
        result = await self.session.scalars(select(Product))
        return [ProductResponse.model_validate(product) for product in result.all()]

    async def get_product_by_id(self, product_id: ProductID) -> ProductResponse | None:
        """Получаем продукт по ID"""
        product = await self.session.get(Product, product_id)
        return ProductResponse.model_validate(product) if product else None

    async def search_products(self, query: str) -> list[ProductResponse]:
        """Поиск по имени и описанию (без учёта регистра)"""
        needle = f"%{query}%"
        py_lower = func.PY_LOWER
        stmt: Select[Tuple[Product]] = select(Product).where(
            or_(
                py_lower(Product.name).like(py_lower(needle)),
                py_lower(Product.description).like(py_lower(needle)),
            )
        )

        result = await self.session.scalars(stmt)
        return [ProductResponse.model_validate(row) for row in result.all()]

    async def get_products_by_category(
        self, category_name: str
    ) -> list[ProductResponse]:
        """Поиск по категории"""
        py_lower = func.PY_LOWER
        stmt: Select[Tuple[Product]] = select(Product).where(
            py_lower(Product.category) == py_lower(category_name)
        )

        result = await self.session.scalars(stmt)
        return [ProductResponse.model_validate(row) for row in result.all()]

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

        result = await self.session.scalars(stmt)
        return [ProductResponse.model_validate(row) for row in result.all()]

    async def create_product(self, request: ProductCreate) -> ProductResponse:
        """Создаём продукт"""
        product = Product(**request.model_dump(), user_id=1)
        self.session.add(product)
        await self.session.commit()
        await self.session.refresh(product)
        return ProductResponse.model_validate(product)

    async def update_product(
        self, product_id: ProductID, request: ProductUpdate
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

    async def delete_product(self, product_id: ProductID) -> ProductResponse | None:
        """Удаляем продукт (True, если удаление прошло)"""
        product = await self.session.get(Product, product_id)
        if not product:
            return None
        snapshot = ProductResponse.model_validate(product)
        await self.session.delete(product)
        await self.session.commit()
        return snapshot


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
        user = await self.session.scalar(select(User).where(User.id == user_id))
        if user is None:
            return None
        user.is_active = active
        await self.session.commit()
        await self.session.refresh(user)
        return user

    async def create(self, data: UserCreate) -> User:
        user = User(**data.model_dump())
        self.session.add(user)
        await self.session.commit()
        await self.session.refresh(user)
        return user


def get_product_repository(session: Session) -> ProductRepository:
    return ProductRepository(session)


def get_user_repository(session: Session) -> UserRepository:
    return UserRepository(session)


ProductRepositoryDI = Annotated[ProductRepository, Depends(get_product_repository)]
UserRepositoryDI = Annotated[UserRepository, Depends(get_user_repository)]
