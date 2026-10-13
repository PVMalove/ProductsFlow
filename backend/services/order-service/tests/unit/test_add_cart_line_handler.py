"""application/commands/add_cart_line.py (issue #369, Seams for TDD #3) —
успех создаёт строку и коммитит; merge на повторном product_id (D4);
невалидный quantity не коммитит."""

import uuid

from kernel_platform.security import Actor, ActorRole

from application.commands import AddCartLineCommand, AddCartLineCommandHandler
from tests.unit.fake_cart_repository import FakeCartRepository
from tests.unit.fake_cart_unit_of_work import FakeCartUnitOfWork

ACTOR = Actor(id=uuid.uuid4(), role=ActorRole.USER)


async def test_add_line_success_creates_and_commits() -> None:
    repo = FakeCartRepository()
    uow = FakeCartUnitOfWork(repo)
    handler = AddCartLineCommandHandler(uow)
    product_id = uuid.uuid4()

    result = await handler.execute(
        AddCartLineCommand(actor=ACTOR, product_id=product_id, quantity=2)
    )

    assert result.is_ok
    assert result.value.product_id == product_id
    assert result.value.quantity == 2
    assert uow.committed is True
    assert len(repo.save_calls) == 1


async def test_add_line_twice_merges_quantity_on_same_product() -> None:
    repo = FakeCartRepository()
    uow = FakeCartUnitOfWork(repo)
    handler = AddCartLineCommandHandler(uow)
    product_id = uuid.uuid4()

    first = await handler.execute(
        AddCartLineCommand(actor=ACTOR, product_id=product_id, quantity=2)
    )
    second = await handler.execute(
        AddCartLineCommand(actor=ACTOR, product_id=product_id, quantity=3)
    )

    assert first.is_ok
    assert second.is_ok
    assert second.value.id == first.value.id
    assert second.value.quantity == 5


async def test_add_line_invalid_quantity_fails_without_committing() -> None:
    repo = FakeCartRepository()
    uow = FakeCartUnitOfWork(repo)
    handler = AddCartLineCommandHandler(uow)

    result = await handler.execute(
        AddCartLineCommand(actor=ACTOR, product_id=uuid.uuid4(), quantity=0)
    )

    assert result.is_err
    assert result.error.code == "invalid_quantity"
    assert uow.committed is False
    assert repo.save_calls == []
