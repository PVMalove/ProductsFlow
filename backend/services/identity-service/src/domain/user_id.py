import uuid
from dataclasses import dataclass
from typing import Any

from kernel_domain.value_object import ValueObject


@dataclass(frozen=True, eq=False)
class UserId(ValueObject):
    """GUID-идентификатор User — намеренное расхождение с `int`-PK монолита
    (ADR TD-01 Фаза 1): identity больше не завязан на автоинкремент БД."""

    value: uuid.UUID

    @classmethod
    def generate(cls) -> "UserId":
        return cls(uuid.uuid4())

    def _equality_components(self) -> tuple[Any, ...]:
        return (self.value,)
