from typing import Annotated, cast

from fastapi import Depends
from sqlalchemy import CursorResult, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import Session
from app.schemas import ProductCreate, ProductID, ProductResponse, ProductUpdate


class ProductRepository:
    """Репозиторий для работы с таблицей products"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_all_products(self) -> list[ProductResponse]:
        """Получаем все продукты"""
        result = await self.session.execute(
            text("SELECT id, name, category, price, description FROM products")
        )
        return [ProductResponse.model_validate(row) for row in result.mappings().all()]

    async def get_product_by_id(self, product_id: ProductID) -> ProductResponse | None:
        """Получаем продукт по ID"""
        result = await self.session.execute(
            text(
                "SELECT id, name, category, price, description "
                "FROM products WHERE id = :id"
            ),
            {"id": product_id},
        )
        row = result.mappings().first()
        return ProductResponse.model_validate(row) if row else None

    async def search_products(self, query: str) -> list[ProductResponse]:
        """Поиск по имени и описанию (без учёта регистра)"""
        needle = f"%{query}%"
        result = await self.session.execute(
            text(
                """
                SELECT id, name, category, price, description
                FROM products
                WHERE PY_LOWER(name) LIKE :needle
                    OR PY_LOWER(description) LIKE :needle
                """
            ),
            {"needle": needle},
        )
        return [ProductResponse.model_validate(row) for row in result.mappings().all()]

    async def get_products_by_category(
        self, category_name: str
    ) -> list[ProductResponse]:
        """Поиск по категории"""
        needle = f"%{category_name}%"
        result = await self.session.execute(
            text(
                """
                SELECT id, name, category, price, description
                FROM products
                WHERE PY_LOWER(category) = :needle
                """
            ),
            {"needle": needle},
        )
        return [ProductResponse.model_validate(row) for row in result.mappings().all()]

    async def get_products_by_price_range(
        self, min_price: float | None, max_price: float | None
    ) -> list[ProductResponse]:
        """Диапазон цен (границы опциональны)"""
        result = await self.session.execute(
            text(
                """
                SELECT id, name, category, price, description
                FROM products
                WHERE (:min_price IS NULL OR price >= :min_price)
                  AND (:max_price IS NULL OR price <= :max_price)
                """
            ),
            {"min_price": min_price, "max_price": max_price},
        )
        return [ProductResponse.model_validate(row) for row in result.mappings().all()]

    async def create_product(self, request: ProductCreate) -> ProductResponse:
        """Создаём продукт"""
        payload = request.model_dump()
        result = await self.session.execute(
            text(
                """
                INSERT INTO products (name, category, price, description)
                VALUES (:name, :category, :price, :description)
                RETURNING id
                """
            ),
            payload,
        )
        product_id = result.scalar_one()
        await self.session.commit()
        return ProductResponse(id=product_id, **payload)

    async def update_product(
        self, product_id: ProductID, request: ProductUpdate
    ) -> bool:
        """Обновляем продукт (True, если обновление прошло)"""
        payload = request.model_dump()
        result = await self.session.execute(
            text(
                """
                UPDATE products
                SET name = :name,
                    category = :category,
                    price = :price,
                    description = :description
                WHERE id = :id
                """
            ),
            {"id": product_id, **payload},
        )
        update_result: CursorResult[tuple[object, ...]] = cast(
            CursorResult[tuple[object, ...]], result
        )
        await self.session.commit()
        return update_result.rowcount > 0

    async def delete_product(self, product_id: ProductID) -> bool:
        """Удаляем продукт (True, если удаление прошло)"""
        result = await self.session.execute(
            text("DELETE FROM products WHERE id = :id"), {"id": product_id}
        )
        delete_result: CursorResult[tuple[object, ...]] = cast(
            CursorResult[tuple[object, ...]], result
        )
        await self.session.commit()
        return delete_result.rowcount > 0


def get_product_repository(session: Session) -> ProductRepository:
    return ProductRepository(session)


ProductRepositoryDI = Annotated[ProductRepository, Depends(get_product_repository)]
