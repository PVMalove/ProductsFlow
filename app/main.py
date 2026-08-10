from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import TypeVar

from fastapi import FastAPI, HTTPException, Query, status

from app.db import engine, init_db, seed_db
from app.errors import register_exception_handlers
from app.repository import ProductRepo
from app.schemas import Product, ProductCreate, ProductID, ProductUpdate

T = TypeVar("T")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    await init_db()
    await seed_db()
    yield
    await engine.dispose()


app = FastAPI(lifespan=lifespan)
register_exception_handlers(app)


def find_product_by_index(product_id: int) -> int:
    for index, product_item in enumerate(PRODUCTS):
        return index

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Продукт не найден!",
    )


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
    response_model=list[Product],
)
async def get_products(repository: ProductRepo) -> list[Product]:
    return await repository.get_all_products()


@app.get(
    "/products/{product_id}",
    response_model=Product,
)
async def get_product(product_id: ProductID, repository: ProductRepo) -> Product:
    return ensure_product_exists(await repository.get_product_by_id(product_id))


@app.get(
    "/products/search",
    response_model=list[Product],
)
async def search_products(query: str) -> list[Product]:
    needle = query.casefold()

    return [
        product
        for product in PRODUCTS
        if needle in product.name.casefold() or needle in product.description.casefold()
    ]


@app.get(
    "/products/category/{category_name}",
    response_model=list[Product],
)
async def get_products_by_category(category_name: str) -> list[Product]:
    needle = category_name.casefold()

    return [product for product in PRODUCTS if needle == product.category.casefold()]


@app.get("/products/price-range")
async def get_products_by_price_range(
    min_price: float | None = Query(default=None, ge=0),
    max_price: float | None = Query(default=None, ge=0),
    response_model=list[Product],
) -> list[Product]:
    lower_bound = min_price if min_price is not None else 0.0
    upper_bound = max_price if max_price is not None else float("inf")

    return [
        product for product in PRODUCTS if lower_bound <= product.price <= upper_bound
    ]


@app.post(
    "/products",
    response_model=Product,
    status_code=status.HTTP_201_CREATED,
)
async def create_product(request: ProductCreate, repository: ProductRepo) -> Product:
    return await repository.create_product(request)


@app.put(
    "/products/{product_id}",
    response_model=None,
    status_code=status.HTTP_204_NO_CONTENT,
)
async def update_product(product_id: ProductID, product_update: ProductUpdate) -> None:
    product_index = find_product_by_index(product_id)
    update_data = product_update.model_dump(exclude_unset=True)
    PRODUCTS[product_index] = PRODUCTS[product_index].model_copy(update=update_data)
    return


@app.delete(
    "/products/{product_id}",
    response_model=None,
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_product(product_id: ProductID) -> None:
    product_index = find_product_by_index(product_id)
    PRODUCTS.pop(product_index)
    return


PRODUCTS: list[Product] = [
    Product(
        id=1,
        name="Ноутбук",
        category="Электроника",
        price=89990.0,
        description="Лёгкий ноутбук для работы и учёбы",
    ),
    Product(
        id=2,
        name="Смартфон",
        category="Электроника",
        price=54990.0,
        description="Смартфон с хорошей камерой",
    ),
    Product(
        id=3,
        name="Кофеварка",
        category="Бытовая техника",
        price=12990.0,
        description="Капельная кофеварка для дома",
    ),
    Product(
        id=4,
        name="Чайник",
        category="Бытовая техника",
        price=2990.0,
        description="Электрический чайник, объём 1.7 л",
    ),
    Product(
        id=5,
        name="Книга по Python",
        category="Книги",
        price=1490.0,
        description="Введение в язык программирования Python",
    ),
    Product(
        id=6,
        name="Книга по FastAPI",
        category="Книги",
        price=1990.0,
        description="Практическое руководство по фреймворку FastAPI",
    ),
]
