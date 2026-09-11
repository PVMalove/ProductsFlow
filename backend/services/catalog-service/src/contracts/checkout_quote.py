"""Framework-independent контракт вывода для авторитетного Checkout Quote
(issue #366) — application-хендлер возвращает его, HTTP только сериализует.
Отдельный от `contracts/product.py`/`ProductView`: не меняет существующие
публичные контракты list/search/get."""

import uuid
from dataclasses import dataclass

from contracts.money import rubles_to_kopecks
from domain.entities.product import Product


@dataclass(frozen=True)
class CheckoutQuoteView:
    product_id: uuid.UUID
    description: str
    unit_price_kopecks: int
    quantity: int
    discount_amount: int = 0

    @classmethod
    def from_domain(cls, product: Product, quantity: int) -> "CheckoutQuoteView":
        return cls(
            product_id=product.id.value,
            description=product.description,
            unit_price_kopecks=rubles_to_kopecks(product.price),
            quantity=quantity,
        )
