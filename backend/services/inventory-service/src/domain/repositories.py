import uuid
from datetime import datetime
from typing import Protocol, runtime_checkable

from kernel_domain.result import Result

from domain.entities.inventory import Inventory
from domain.entities.reservation import Reservation


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

    async def reserve(
        self, product_id: uuid.UUID, quantity: int
    ) -> Result[Inventory] | None:
        """`None` — запись остатка для `product_id` не найдена (issue #370)."""
        ...

    async def release(
        self, product_id: uuid.UUID, quantity: int
    ) -> Result[Inventory] | None:
        """`None` — запись остатка для `product_id` не найдена (issue #370)."""
        ...


@runtime_checkable
class ReservationRepository(Protocol):
    """Контракт персистентности агрегата Reservation (ADR 0006, issue #370)."""

    async def get_by_order_id(self, order_id: uuid.UUID) -> Reservation | None: ...

    async def try_create(self, reservation: Reservation) -> bool:
        """Идемпотентно создаёт резерв (натуральная PK-идемпотентность на
        `order_id`, D3). Возвращает `True`, если резерв был реально вставлен,
        `False` — при уже существующем."""
        ...

    async def claim_expired(self, *, now: datetime, limit: int) -> list[Reservation]:
        """`SELECT ... FOR UPDATE SKIP LOCKED` по просроченным `ACTIVE`-резервам
        (D6) — строки уже заблокированы в текущей транзакции вызывающего."""
        ...

    async def save(self, reservation: Reservation) -> None: ...
