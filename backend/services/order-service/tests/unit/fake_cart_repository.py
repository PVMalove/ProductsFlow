"""Фейковый CartRepository для юнит-тестов application handler'ов (issue #369)."""

import uuid

from domain.entities.cart import Cart


class FakeCartRepository:
    def __init__(self, carts: list[Cart] | None = None) -> None:
        self._by_user_id: dict[uuid.UUID, Cart] = {
            cart.user_id: cart for cart in (carts or [])
        }
        self.save_calls: list[Cart] = []

    async def get_or_create_for_user(self, user_id: uuid.UUID) -> Cart:
        cart = self._by_user_id.get(user_id)
        if cart is None:
            from domain.value_objects.cart_id import CartId

            cart = Cart.create(CartId.new_id(), user_id=user_id)
            self._by_user_id[user_id] = cart
        return cart

    async def get_for_user(self, user_id: uuid.UUID) -> Cart | None:
        return self._by_user_id.get(user_id)

    async def get_line_owner(self, line_id: uuid.UUID) -> Cart | None:
        for cart in self._by_user_id.values():
            if any(line.id == line_id for line in cart.lines):
                return cart
        return None

    async def save(self, cart: Cart) -> None:
        self.save_calls.append(cart)
        self._by_user_id[cart.user_id] = cart
