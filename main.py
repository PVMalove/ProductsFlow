from typing import Any, Optional

from fastapi import FastAPI, HTTPException, status

app = FastAPI()


@app.get("/health")
async def health_check():
    return {"status": "ok"}


@app.get("/products")
async def get_products():
    return PRODUCTS


@app.get("/products/search")
async def search_products(query: str):
    needle = query.casefold()

    return [
        product
        for product in PRODUCTS
        if needle in product.get("name", "").casefold()
        or needle in product.get("description", "").casefold()
    ]


@app.get("/products/category/{category_name}")
async def get_products_by_category(category_name: str):
    needle = category_name.casefold()

    return [
        product
        for product in PRODUCTS
        if needle == product.get("category", "").casefold()
    ]


@app.get("/products/price-range")
async def get_products_by_price_range(
    min_price: Optional[float] = None, max_price: Optional[float] = None
):
    lower_bound = min_price if min_price is not None else 0.0
    upper_bound = max_price if max_price is not None else float("inf")
    
    return [
        product
        for product in PRODUCTS
        if lower_bound <= product.get("price", 0.0) <= upper_bound
    ]


@app.get("/products/{product_id}")
async def get_product(product_id: int):
    product = next((p for p in PRODUCTS if p["id"] == product_id), None)

    if product is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Продукт не найден!",
        )

    return product


PRODUCTS: list[dict[str, Any]] = [
    {
        "id": 1,
        "name": "Ноутбук",
        "category": "Электроника",
        "price": 89990.0,
        "description": "Лёгкий ноутбук для работы и учёбы",
    },
    {
        "id": 2,
        "name": "Смартфон",
        "category": "Электроника",
        "price": 54990.0,
        "description": "Смартфон с хорошей камерой",
    },
    {
        "id": 3,
        "name": "Кофеварка",
        "category": "Бытовая техника",
        "price": 12990.0,
        "description": "Капельная кофеварка для дома",
    },
    {
        "id": 4,
        "name": "Чайник",
        "category": "Бытовая техника",
        "price": 2990.0,
        "description": "Электрический чайник, объём 1.7 л",
    },
    {
        "id": 5,
        "name": "Книга по Python",
        "category": "Книги",
        "price": 1490.0,
        "description": "Введение в язык программирования Python",
    },
    {
        "id": 6,
        "name": "Книга по FastAPI",
        "category": "Книги",
        "price": 1990.0,
        "description": "Практическое руководство по фреймворку FastAPI",
    },
]
