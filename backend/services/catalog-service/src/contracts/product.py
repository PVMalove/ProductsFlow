"""Framework-independent контракты вывода для команд товаров catalog
(ADR 0002) — application-хендлеры возвращают их, HTTP только сериализует."""

import uuid
from dataclasses import dataclass

from domain.entities.product import Product


@dataclass(frozen=True)
class ProductView:
    id: uuid.UUID
    name: str
    description: str
    price: float
    category: str
    user_id: uuid.UUID
    is_active: bool
    # Populated after the fact by list/search handlers (see
    # application.queries.attach_image_urls) — never set here, so a cached
    # search page (infrastructure/search/cache.py) never freezes in a
    # presigned URL that could outlive its expiry.
    image_url: str | None = None

    @classmethod
    def from_domain(cls, product: Product) -> "ProductView":
        return cls(
            id=product.id.value,
            name=product.name,
            description=product.description,
            price=product.price,
            category=product.category,
            user_id=product.user_id,
            is_active=product.is_active,
        )
