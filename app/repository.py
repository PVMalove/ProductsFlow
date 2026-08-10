from typing import Annotated, Any

from fastapi import Depends
from sqlalchemy import Row, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import Session
from app.schemas import Product, ProductCreate, ProductID


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
                WHERE py_lower(name) LIKE :needle
                OR py_lower(description) LIKE :needle
                """
            ),
            {"needle": needle},
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


def get_product_repository(session: Session) -> ProductRepository:
    return ProductRepository(session)


ProductRepo = Annotated[ProductRepository, Depends(get_product_repository)]
