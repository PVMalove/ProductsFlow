import uuid
from dataclasses import dataclass
from typing import Any

from kernel_domain.value_object import ValueObject


@dataclass(frozen=True, eq=False)
class ProductId(ValueObject):
    """GUID-обёртка первичного ключа агрегата `Product` (ADR 0024)."""

    value: uuid.UUID

    @classmethod
    def generate(cls) -> "ProductId":
        return cls(uuid.uuid4())

    def _equality_components(self) -> tuple[Any, ...]:
        return (self.value,)
