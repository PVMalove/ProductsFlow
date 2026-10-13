import uuid
from dataclasses import dataclass
from typing import Any, cast

from kernel_domain.value_object import ValueObject

from domain.value_objects import PRIVATE_MARKER

_MISSING = object()


@dataclass(frozen=True, eq=False)
class CartId(ValueObject):
    """GUID-обёртка первичного ключа агрегата `Cart` (по образцу
    `ProductId`/`TicketId`)."""

    value: uuid.UUID

    def __init__(
        self, marker: object = _MISSING, value: uuid.UUID = cast("uuid.UUID", _MISSING)
    ) -> None:
        if marker is not PRIVATE_MARKER:
            raise RuntimeError(
                "CartId instances must be created through "
                "CartId.new_id()/CartId.create()"
            )
        object.__setattr__(self, "value", value)

    @classmethod
    def new_id(cls) -> "CartId":
        return cls(PRIVATE_MARKER, uuid.uuid4())

    @classmethod
    def create(cls, value: uuid.UUID) -> "CartId":
        return cls(PRIVATE_MARKER, value)

    def _equality_components(self) -> tuple[Any, ...]:
        return (self.value,)
