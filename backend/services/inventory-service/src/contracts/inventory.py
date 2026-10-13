"""Framework-independent контракт вывода для команд inventory (ADR 0002) —
application-хендлеры возвращают его, HTTP только сериализует."""

import uuid
from dataclasses import dataclass

from domain.entities.inventory import Inventory


@dataclass(frozen=True)
class InventoryView:
    product_id: uuid.UUID
    quantity: int

    @classmethod
    def from_domain(cls, inventory: Inventory) -> "InventoryView":
        return cls(product_id=inventory.id, quantity=inventory.quantity)
