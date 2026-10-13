"""Фейковый InventoryRepository для юнит-тестов reservation-хендлеров
(issue #370) — покрывает `reserve()`/`release()`, оставляя
`create_zero()`/`adjust()` не реализованными (не нужны в этом контексте,
тот же приём, что `test_adjust_inventory_stock_handler.py`'s
`FakeInventoryRepository` для #367 делает в обратную сторону)."""

import uuid

from kernel_domain.result import Result

from domain.entities.inventory import Inventory


class FakeInventoryRepository:
    def __init__(self, inventories: list[Inventory] | None = None) -> None:
        self._by_product_id: dict[uuid.UUID, Inventory] = {
            inventory.id: inventory for inventory in (inventories or [])
        }
        self.reserve_calls: list[tuple[uuid.UUID, int]] = []
        self.release_calls: list[tuple[uuid.UUID, int]] = []

    async def get_by_product_id(self, product_id: uuid.UUID) -> Inventory | None:
        return self._by_product_id.get(product_id)

    async def create_zero(self, product_id: uuid.UUID) -> bool:
        raise NotImplementedError

    async def adjust(
        self, product_id: uuid.UUID, delta: int, *, reason: str
    ) -> Result[Inventory] | None:
        raise NotImplementedError

    async def reserve(
        self, product_id: uuid.UUID, quantity: int
    ) -> Result[Inventory] | None:
        self.reserve_calls.append((product_id, quantity))
        inventory = self._by_product_id.get(product_id)
        if inventory is None:
            return None
        result = inventory.reserve(quantity)
        if result.is_err:
            return Result[Inventory].fail(result.error)
        return Result[Inventory].ok(inventory)

    async def release(
        self, product_id: uuid.UUID, quantity: int
    ) -> Result[Inventory] | None:
        self.release_calls.append((product_id, quantity))
        inventory = self._by_product_id.get(product_id)
        if inventory is None:
            return None
        result = inventory.release(quantity)
        if result.is_err:
            return Result[Inventory].fail(result.error)
        return Result[Inventory].ok(inventory)
