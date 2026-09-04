import uuid
from dataclasses import dataclass
from typing import Any, cast

from kernel_domain.value_object import ValueObject

from domain.value_objects import PRIVATE_MARKER

_MISSING = object()


@dataclass(frozen=True, eq=False)
class ProductId(ValueObject):
    """GUID-обёртка первичного ключа агрегата `Product` (ADR 0006)."""

    value: uuid.UUID

    def __init__(
        self, marker: object = _MISSING, value: uuid.UUID = cast("uuid.UUID", _MISSING)
    ) -> None:
        if marker is not PRIVATE_MARKER:
            raise RuntimeError(
                "ProductId instances must be created through "
                "ProductId.new_id()/ProductId.create()"
            )
        object.__setattr__(self, "value", value)

    @classmethod
    def new_id(cls) -> "ProductId":
        return cls(PRIVATE_MARKER, uuid.uuid4())

    @classmethod
    def create(cls, value: uuid.UUID) -> "ProductId":
        return cls(PRIVATE_MARKER, value)

    def _equality_components(self) -> tuple[Any, ...]:
        return (self.value,)
