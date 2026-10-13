"""application/commands/remove_cart_line.py (issue #369, Seams for TDD #3) —
тот же ownership-порядок, что и update: 403 до мутации, 404 для несуществующей
строки (D5/D7)."""

import uuid
from datetime import UTC, datetime

import pytest
from kernel_platform.security import Actor, ActorRole

from application.commands import RemoveCartLineCommand, RemoveCartLineCommandHandler
from application.errors import CartAccessDeniedError, CartLineNotFoundError
from domain.entities.cart import Cart
from domain.value_objects.cart_id import CartId
from tests.unit.fake_cart_repository import FakeCartRepository
from tests.unit.fake_cart_unit_of_work import FakeCartUnitOfWork

OWNER_ID = uuid.uuid4()
OTHER_USER_ID = uuid.uuid4()


def _cart_with_line() -> tuple[Cart, uuid.UUID]:
    cart = Cart.create(CartId.new_id(), user_id=OWNER_ID)
    line_id = uuid.uuid4()
    result = cart.add_line(
        line_id=line_id, product_id=uuid.uuid4(), quantity=1, now=datetime.now(UTC)
    )
    assert result.is_ok
    return cart, line_id


async def test_remove_by_owner_succeeds() -> None:
    cart, line_id = _cart_with_line()
    repo = FakeCartRepository([cart])
    uow = FakeCartUnitOfWork(repo)
    handler = RemoveCartLineCommandHandler(uow)
    actor = Actor(id=OWNER_ID, role=ActorRole.USER)

    result = await handler.execute(RemoveCartLineCommand(actor=actor, line_id=line_id))

    assert result.is_ok
    assert cart.lines == []
    assert uow.committed is True


async def test_remove_by_another_user_is_denied_before_any_mutation() -> None:
    cart, line_id = _cart_with_line()
    repo = FakeCartRepository([cart])
    uow = FakeCartUnitOfWork(repo)
    handler = RemoveCartLineCommandHandler(uow)
    other_actor = Actor(id=OTHER_USER_ID, role=ActorRole.USER)

    with pytest.raises(CartAccessDeniedError):
        await handler.execute(RemoveCartLineCommand(actor=other_actor, line_id=line_id))

    assert len(cart.lines) == 1
    assert uow.committed is False
    assert repo.save_calls == []


async def test_remove_unknown_line_raises_not_found() -> None:
    repo = FakeCartRepository()
    uow = FakeCartUnitOfWork(repo)
    handler = RemoveCartLineCommandHandler(uow)
    actor = Actor(id=OWNER_ID, role=ActorRole.USER)

    with pytest.raises(CartLineNotFoundError):
        await handler.execute(RemoveCartLineCommand(actor=actor, line_id=uuid.uuid4()))
