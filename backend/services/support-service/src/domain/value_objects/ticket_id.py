# ruff: noqa: E501
import uuid
from dataclasses import dataclass
from typing import Any, cast

from kernel_domain.value_object import ValueObject

from domain.value_objects import _PRIVATE_MARKER

_MISSING = object()


@dataclass(frozen=True, eq=False)
class TicketId(ValueObject):
    """GUID-обёртка первичного ключа агрегата `Ticket` (по образцу `ProductId`/`UserId`)."""

    value: uuid.UUID

    def __init__(
        self, marker: object = _MISSING, value: uuid.UUID = cast("uuid.UUID", _MISSING)
    ) -> None:
        if marker is not _PRIVATE_MARKER:
            raise RuntimeError(
                "TicketId instances must be created through "
                "TicketId.new_id()/TicketId.create()"
            )
        object.__setattr__(self, "value", value)

    @classmethod
    def new_id(cls) -> "TicketId":
        return cls(_PRIVATE_MARKER, uuid.uuid4())

    @classmethod
    def create(cls, value: uuid.UUID) -> "TicketId":
        return cls(_PRIVATE_MARKER, value)

    def _equality_components(self) -> tuple[Any, ...]:
        return (self.value,)
