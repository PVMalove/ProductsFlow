"""application/commands/adjust_inventory_stock.py — по образцу catalog's
test_product_handlers.py: success, отрицательный итог, несуществующий
product_id (issue #367, Seams for TDD #4)."""

import uuid

from kernel_domain.result import Result
from kernel_platform.security import Actor, ActorRole

from application.commands import (
    AdjustInventoryStockCommand,
    AdjustInventoryStockCommandHandler,
)
from contracts.inventory import InventoryView
from domain.entities.inventory import Inventory
from tests.unit.fake_inventory_unit_of_work import FakeInventoryUnitOfWork

PRODUCT_ID = uuid.uuid4()
ADMIN = Actor(id=uuid.uuid4(), role=ActorRole.ADMIN)


class FakeInventoryRepository:
    def __init__(self, inventory: Inventory | None = None) -> None:
        self.inventory = inventory
        self.adjust_calls: list[tuple[uuid.UUID, int, str]] = []

    async def get_by_product_id(self, product_id: uuid.UUID) -> Inventory | None:
        return self.inventory

    async def create_zero(self, product_id: uuid.UUID) -> bool:
        raise NotImplementedError

    async def adjust(self, product_id: uuid.UUID, delta: int, *, reason: str):
        self.adjust_calls.append((product_id, delta, reason))
        if self.inventory is None or self.inventory.id != product_id:
            return None
        result = self.inventory.adjust(delta)
        if result.is_err:
            return Result[Inventory].fail(result.error)
        return Result[Inventory].ok(self.inventory)


async def test_adjust_inventory_stock_succeeds_and_commits() -> None:
    inventory = Inventory.create_zero(PRODUCT_ID)
    repo = FakeInventoryRepository(inventory)
    uow = FakeInventoryUnitOfWork(repo)
    handler = AdjustInventoryStockCommandHandler(uow)

    result = await handler.execute(
        AdjustInventoryStockCommand(
            actor=ADMIN, product_id=PRODUCT_ID, delta=5, reason="пересчёт"
        )
    )

    assert result.is_ok
    assert result.value == InventoryView(product_id=PRODUCT_ID, quantity=5)
    assert repo.adjust_calls == [(PRODUCT_ID, 5, "пересчёт")]
    assert uow.committed is True


async def test_adjust_inventory_stock_rejects_negative_result_without_commit() -> None:
    inventory = Inventory.create_zero(PRODUCT_ID)
    repo = FakeInventoryRepository(inventory)
    uow = FakeInventoryUnitOfWork(repo)
    handler = AdjustInventoryStockCommandHandler(uow)

    result = await handler.execute(
        AdjustInventoryStockCommand(
            actor=ADMIN, product_id=PRODUCT_ID, delta=-10, reason="ошибка учёта"
        )
    )

    assert result.is_err
    assert result.error.code == "negative_stock_adjustment"
    assert uow.committed is False
    assert uow.rolled_back is True


async def test_adjust_inventory_stock_fails_for_unknown_product() -> None:
    repo = FakeInventoryRepository(None)
    uow = FakeInventoryUnitOfWork(repo)
    handler = AdjustInventoryStockCommandHandler(uow)

    result = await handler.execute(
        AdjustInventoryStockCommand(
            actor=ADMIN, product_id=uuid.uuid4(), delta=1, reason="?"
        )
    )

    assert result.is_err
    assert result.error.code == "inventory_not_found"
    assert uow.committed is False
