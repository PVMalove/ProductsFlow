from typing import Any, Dict, List

from fastapi import FastAPI, HTTPException, Query, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.schemas import Product, ProductCreate, ProductID, ProductUpdate

app = FastAPI()


VALIDATION_MESSAGES: Dict[tuple[str, str], str] = {
    ("name", "string_type"): "Название продукта должно быть строкой",
    ("name", "string_too_short"): "Название продукта слишком короткое",
    ("name", "string_too_long"): "Название продукта слишком длинное",
    ("category", "string_type"): "Категория продукта должна быть строкой",
    ("category", "string_too_short"): "Категория продукта слишком короткая",
    ("category", "string_too_long"): "Категория продукта слишком длинная",
    ("price", "greater_than_equal"): "Цена продукта должна быть положительным числом",
    ("product_id", "greater_than"): "ID продукта должен быть положительным числом"
}


def find_product_by_index(product_id: int) -> int:
    for index, product_item in enumerate(PRODUCTS):
            return index

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Продукт не найден!",
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    _request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    errors: List[Dict[str, Any]] = []

    for error in exc.errors():
        loc = list(error["loc"])
        field_key = ".".join(map(str, loc[1:])) if len(loc) > 1 else loc[-1]
        message = VALIDATION_MESSAGES.get((field_key, error["type"]), error["msg"])
        errors.append(
            {
                "field": field_key,
                "type": error["type"],
                "message": message,
            }
        )

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content={"detail": errors},
    )


@app.get("/health")
async def health_check() -> dict[str, str]:
    return {"status": "ok"}


@app.get(
    "/products",
    response_model=list[Product],
)
async def get_products() -> list[Product]:
    return PRODUCTS


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


@app.get(
    "/products/{product_id}",
    response_model=Product,
)
async def get_product(product_id: ProductID) -> Product:
    product_index = find_product_by_index(product_id)
    return PRODUCTS[product_index]


@app.post(
    "/products",
    response_model=Product,
    status_code=status.HTTP_201_CREATED,
)
async def create_product(product_create: ProductCreate) -> Product:
    new_id = max(p.id for p in PRODUCTS) + 1 if PRODUCTS else 1
    product_instance = Product(id=new_id, **product_create.model_dump())
    PRODUCTS.append(product_instance)
    return product_instance


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
