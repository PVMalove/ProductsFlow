"""Framework-independent контракт вывода для команд/запросов cart
(ADR 0002) — application-хендлеры возвращают его, HTTP только сериализует."""

import uuid
from dataclasses import dataclass
from datetime import datetime

from domain.entities.cart import Cart
from domain.entities.cart_line import CartLine


@dataclass(frozen=True)
class CartLineView:
    id: uuid.UUID
    product_id: uuid.UUID
    quantity: int
    added_at: datetime

    @classmethod
    def from_domain(cls, line: CartLine) -> "CartLineView":
        return cls(
            id=line.id,
            product_id=line.product_id,
            quantity=line.quantity,
            added_at=line.added_at,
        )


@dataclass(frozen=True)
class CartView:
    lines: list[CartLineView]

    @classmethod
    def from_domain(cls, cart: Cart) -> "CartView":
        return cls(lines=[CartLineView.from_domain(line) for line in cart.lines])

    @classmethod
    def empty(cls) -> "CartView":
        # D3: корзина без строки в БД возвращает пустой CartView, без
        # побочного эффекта записи.
        return cls(lines=[])
