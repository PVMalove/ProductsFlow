from typing import Annotated, Any, cast

from fastapi import Depends
from sqlalchemy import CursorResult, Row, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import Session
from app.schemas import Product, ProductCreate, ProductID, ProductUpdate


class ProductRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session: AsyncSession = session

    async def get_all_products(self) -> list[Product]:
        result = await self.session.execute(
            text("SELECT id, name, category, price, description FROM products")
        )
        return [Product.model_validate(row._mapping) for row in result.fetchall()]

    async def get_product_by_id(self, product_id: ProductID) -> Product | None:
        result = await self.session.execute(
            text(
                """SELECT id, name, category, price, description
                FROM products
                WHERE id = :id"""
            ),
            {"id": product_id},
        )
        row: Row[Any] | None = result.fetchone()
        if row is None:
            return None
        return Product.model_validate(row._mapping)

    async def search_products(self, query: str) -> list[Product]:
        needle = f"%{query.casefold()}%"
        result = await self.session.execute(
            text(
                """SELECT id, name, category, price, description
                FROM products
                WHERE PY_LOWER(name) LIKE :needle
                OR PY_LOWER(description) LIKE :needle
                """
            ),
            {"needle": needle},
        )
        return [Product.model_validate(row._mapping) for row in result.fetchall()]

    async def get_products_by_category(self, category_name: str) -> list[Product]:
        needle = category_name.casefold()
        result = await self.session.execute(
            text(
                """SELECT id, name, category, price, description
                FROM products
                WHERE PY_LOWER(category) = :needle"""
            ),
            {"needle": needle},
        )
        return [Product.model_validate(row._mapping) for row in result.fetchall()]

    async def get_products_by_price_range(
        self, min_price: float | None, max_price: float | None
    ) -> list[Product]:
        lower_bound = min_price if min_price is not None else 0.0
        upper_bound = max_price if max_price is not None else float("inf")

        result = await self.session.execute(
            text(
                """SELECT id, name, category, price, description
                FROM products
                WHERE price BETWEEN :lower AND :upper"""
            ),
            {"lower": lower_bound, "upper": upper_bound},
        )
        return [Product.model_validate(row._mapping) for row in result.fetchall()]

    async def create_product(self, request: ProductCreate) -> Product:
        payload = request.model_dump()
        result = await self.session.execute(
            text("""
                INSERT INTO products (name, category, price, description)
                VALUES (:name, :category, :price, :description)
                RETURNING id
            """),
            payload,
        )

        product_id = result.scalar_one()
        await self.session.commit()
        return Product(id=product_id, **payload)

    async def update_product(
        self, product_id: ProductID, request: ProductUpdate
    ) -> bool:
        payload = request.model_dump()
        result = await self.session.execute(
            text("""
                UPDATE products
                SET name = :name,
                    category = :category,
                    price = :price,
                    description = :description
                WHERE id = :id
                RETURNING id
            """),
            {"id": product_id, **payload},
        )

        update_result: CursorResult[tuple[ProductID]] = cast(
            CursorResult[tuple[ProductID]], result
        )

        await self.session.commit()
        return update_result.rowcount > 0


def get_product_repository(session: Session) -> ProductRepository:
    return ProductRepository(session)


ProductRepo = Annotated[ProductRepository, Depends(get_product_repository)]
