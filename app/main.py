from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import TypeVar

from fastapi import FastAPI, HTTPException, Query, status

from app.db import engine, init_db, seed_db
from app.errors import register_exception_handlers
from app.repository import ProductRepositoryDI
from app.schemas import ProductCreate, ProductID, ProductResponse, ProductUpdate

T = TypeVar("T")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    await init_db()
    await seed_db()
    yield
    await engine.dispose()


app = FastAPI(lifespan=lifespan)
register_exception_handlers(app)


def ensure_product_exists(entity: T | None) -> T:
    if not entity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Продукт не найден!",
        )
    return entity


@app.get("/health")
async def health_check() -> dict[str, str]:
    return {"status": "ok"}


@app.get(
    "/products",
    response_model=list[ProductResponse],
)
async def get_products(repository: ProductRepositoryDI) -> list[ProductResponse]:
    return await repository.get_all_products()


@app.get(
    "/products/search",
    response_model=list[ProductResponse],
)
async def search_products(
    query: str, repository: ProductRepositoryDI
) -> list[ProductResponse]:
    return await repository.search_products(query)


@app.get(
    "/products/{product_id}",
    response_model=ProductResponse,
)
async def get_product(
    product_id: ProductID, repository: ProductRepositoryDI
) -> ProductResponse:
    return ensure_product_exists(await repository.get_product_by_id(product_id))


@app.get(
    "/products/category/{category_name}",
    response_model=list[ProductResponse],
)
async def get_products_by_category(
    category_name: str, repository: ProductRepositoryDI
) -> list[ProductResponse]:
    return await repository.get_products_by_category(category_name)


@app.get(
    "/products/price-range",
    response_model=list[ProductResponse],
)
async def get_products_by_price_range(
    repository: ProductRepositoryDI,
    min_price: float | None = Query(default=None, ge=0),
    max_price: float | None = Query(default=None, ge=0),
) -> list[ProductResponse]:
    return await repository.get_products_by_price_range(min_price, max_price)


@app.post(
    "/products",
    response_model=ProductResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_product(
    request: ProductCreate, repository: ProductRepositoryDI
) -> ProductResponse:
    return await repository.create_product(request)


@app.put(
    "/products/{product_id}",
    response_model=None,
    status_code=status.HTTP_204_NO_CONTENT,
)
async def update_product(
    product_id: ProductID,
    product_update: ProductUpdate,
    repository: ProductRepositoryDI,
) -> bool:
    return ensure_product_exists(
        await repository.update_product(product_id, product_update)
    )


@app.delete(
    "/products/{product_id}",
    response_model=None,
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_product(
    product_id: ProductID, repository: ProductRepositoryDI
) -> bool:
    return ensure_product_exists(await repository.delete_product(product_id))
