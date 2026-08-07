from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel, Field

app = FastAPI()


class ProductBase(BaseModel):
    name: str = Field(min_length=1, max_length=100, description="Название продукта")
    category: str = Field(
        min_length=1, max_length=100, description="Категория продукта"
    )
    price: float = Field(..., ge=0, description="Цена продукта")
    description: str = ""


class ProductCreate(ProductBase):
    pass


class ProductUpdate(BaseModel):
    name: str | None = Field(
        default=None, min_length=1, max_length=100, description="Название продукта"
    )
    category: str | None = Field(
        default=None, min_length=1, max_length=100, description="Категория продукта"
    )
    price: float | None = Field(default=None, ge=0, description="Цена продукта")
    description: str = ""


class Product(ProductBase):
    id: int


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
    min_price: float | None = None,
    max_price: float | None = None,
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
async def get_product(product_id: int) -> Product:
    product: Product | None = next((p for p in PRODUCTS if p.id == product_id), None)

    if product is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Продукт не найден!",
        )

    return product


@app.post(
    "/products",
    response_model=Product,
    status_code=status.HTTP_201_CREATED,
)
async def create_product(product_create: ProductCreate) -> Product:

    # "field required": "name",
    # "error_messages": "Название продукта не может быть пустым.",
    # "field required": "category",
    # "error_messages": "Категория продукта не может быть пустой.",
    # "field required": "price",
    # "error_messages": "Цена продукта должна быть положительным числом.",

    new_id = max(p.id for p in PRODUCTS) + 1 if PRODUCTS else 1
    product_data = product_create.model_dump()
    product_data["id"] = new_id
    product_instance = Product(**product_data)
    PRODUCTS.append(product_instance)
    return product_instance


@app.put(
    "/products/{product_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def update_product(product_id: int, product_update: ProductUpdate) -> None:
    product_index: int | None = None
    for index, product_item in enumerate(PRODUCTS):
        if product_item.id == product_id:
            product_index = index
            break

    if product_index is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Продукт не найден!",
        )

    # "field required": "name",
    # "error_messages": "Название продукта не может быть пустым.",
    # "field required": "category",
    # "error_messages": "Категория продукта не может быть пустой.",
    # "field required": "price",
    # "error_messages": "Цена продукта должна быть положительным числом.",

    update_data = product_update.model_dump(exclude_unset=True)
    PRODUCTS[product_index] = PRODUCTS[product_index].model_copy(update=update_data)
    return


@app.delete("/products/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_product(product_id: int) -> None:
    product_index: int | None = None
    for index, product_item in enumerate(PRODUCTS):
        if product_item.id == product_id:
            product_index = index
            break

    if product_index is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Продукт не найден!",
        )

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
