"""application/queries/get_cart.py (issue #369) — GET без побочного эффекта
записи (D3): корзина без строки в БД возвращает пустой `CartView`."""

import uuid
from datetime import UTC, datetime

from application.queries import GetCartQuery, GetCartQueryHandler
from domain.entities.cart import Cart
from domain.value_objects.cart_id import CartId
from tests.unit.fake_cart_repository import FakeCartRepository

USER_ID = uuid.uuid4()


async def test_get_cart_for_unknown_user_returns_empty_view() -> None:
    repo = FakeCartRepository()
    handler = GetCartQueryHandler(repo)

    result = await handler.execute(GetCartQuery(user_id=USER_ID))

    assert result.is_ok
    assert result.value.lines == []


async def test_get_cart_returns_existing_lines() -> None:
    cart = Cart.create(CartId.new_id(), user_id=USER_ID)
    cart.add_line(
        line_id=uuid.uuid4(), product_id=uuid.uuid4(), quantity=2, now=datetime.now(UTC)
    )
    repo = FakeCartRepository([cart])
    handler = GetCartQueryHandler(repo)

    result = await handler.execute(GetCartQuery(user_id=USER_ID))

    assert result.is_ok
    assert len(result.value.lines) == 1
    assert result.value.lines[0].quantity == 2
