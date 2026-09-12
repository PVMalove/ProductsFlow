import uuid
from typing import cast

from kernel_domain import PRIVATE_MARKER
from kernel_domain.entity import Entity
from kernel_domain.result import Result

from domain.errors import InventoryErrors
from domain.events.inventory_domain_event import InventoryAdjusted

_MISSING = object()


class Inventory(Entity[uuid.UUID]):
    """Агрегат остатка товара (ADR 0016, issue #367). PK = `product_id` —
    не отдельный синтетический id: закрепляет инвариант «один Inventory
    Pool на продукт» уже на уровне схемы, не только в бизнес-логике.

    Конструктор вызывается только через `create_zero()` (product lifecycle)
    или `reconstitute()` (гидратация из БД) — маркер приватности проверяется
    централизованно в `Entity.__init__`."""

    def __init__(
        self,
        marker: object = _MISSING,
        id: uuid.UUID = cast("uuid.UUID", _MISSING),
        *,
        quantity: int,
        reserved: int = 0,
    ) -> None:
        super().__init__(marker, id=id)
        self.quantity = quantity
        self.reserved = reserved

    @classmethod
    def create_zero(cls, product_id: uuid.UUID) -> "Inventory":
        """Нулевой остаток, создаваемый идемпотентным Product-lifecycle
        консьюмером. Без доменного события — намеренная асимметрия с
        `ProductCreated`: сегодня никто не должен знать «у товара появился
        inventory pool» как отдельный факт (Trade-offs брифа #367)."""
        return cls(PRIVATE_MARKER, product_id, quantity=0)

    @classmethod
    def reconstitute(
        cls, product_id: uuid.UUID, *, quantity: int, reserved: int = 0
    ) -> "Inventory":
        return cls(PRIVATE_MARKER, product_id, quantity=quantity, reserved=reserved)

    def adjust(self, delta: int) -> Result[None]:
        """Always-Valid Domain: неотрицательность ДОСТУПНОГО остатка — это
        инвариант самого агрегата, не только API/schema-границы (issue #367,
        риск 3). Issue #370 (архитектурный бриф, находка 5) расширяет
        инвариант: итоговый quantity не может опуститься ниже уже
        зарезервированного — при `reserved=0` условие математически
        эквивалентно прежнему `< 0`."""
        new_quantity = self.quantity + delta
        if new_quantity < self.reserved:
            return Result[None].fail(InventoryErrors.negative_stock_adjustment())

        self.quantity = new_quantity
        self.add_domain_event(
            InventoryAdjusted(
                product_id=self.id,
                delta=delta,
                quantity_after=self.quantity,
            )
        )
        return Result[None].ok(None)

    def reserve(self, quantity: int) -> Result[None]:
        """Резервирует часть доступного остатка (issue #370, ADR 0016).
        Always-Valid Domain: доступность (`quantity - reserved`) проверяется
        здесь, не на границе репозитория/приложения. Без доменного события —
        та же намеренная асимметрия, что `create_zero()` (issue #367
        Trade-offs): интересный внешнему миру факт живёт на уровне
        `Reservation` (что случилось с ЗАКАЗОМ), не отдельного товара."""
        available = self.quantity - self.reserved
        if quantity > available:
            return Result[None].fail(InventoryErrors.insufficient_available_stock())

        self.reserved += quantity
        return Result[None].ok(None)

    def release(self, quantity: int) -> Result[None]:
        """Возвращает ранее зарезервированное количество в доступный остаток.
        `quantity > reserved` не ожидается в нормальном потоке (releases
        всегда releases то, что сам же reserve() до этого зарезервировал) —
        защитный инвариант, не исключение."""
        if quantity > self.reserved:
            return Result[None].fail(InventoryErrors.insufficient_available_stock())

        self.reserved -= quantity
        return Result[None].ok(None)
