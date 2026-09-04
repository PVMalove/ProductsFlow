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
