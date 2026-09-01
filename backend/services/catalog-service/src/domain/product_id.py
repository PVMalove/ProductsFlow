from dataclasses import dataclass
from typing import Any

from kernel_domain.value_object import ValueObject


@dataclass(frozen=True, eq=False)
class ProductId(ValueObject):
    """PK-обёртка `products.id` (bigint, генерируется Postgres-последовательностью
    — не GUID, в отличие от `identity.UserId`): `OutboxMessage.aggregate_id`
    (`kernel_platform`) типизирован `BigInteger`, менять это вне
    catalog-service запрещено ADR 0021."""

    value: int

    def _equality_components(self) -> tuple[Any, ...]:
        return (self.value,)
