import uuid
from typing import Protocol, runtime_checkable

from kernel_domain.result import Result

from domain.entities.inventory import Inventory


@runtime_checkable
class InventoryRepository(Protocol):
    """Контракт персистентности агрегата Inventory (ADR 0006, issue #367)."""

    async def get_by_product_id(self, product_id: uuid.UUID) -> Inventory | None: ...

    async def create_zero(self, product_id: uuid.UUID) -> bool:
        """Идемпотентно создаёт нулевую запись. Возвращает `True`, если
        строка была реально вставлена, `False` — при уже существующей
        (natural PK-идемпотентность, issue #367 риск 2)."""
        ...

    async def adjust(
        self, product_id: uuid.UUID, delta: int, *, reason: str
    ) -> Result[Inventory] | None:
        """`None` — запись остатка для `product_id` не найдена."""
        ...
