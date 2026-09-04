import uuid
from dataclasses import dataclass
from typing import Any, cast

from kernel_domain.value_object import ValueObject

from domain.value_objects import _PRIVATE_MARKER

_MISSING = object()


@dataclass(frozen=True, eq=False)
class UserId(ValueObject):
    """GUID-идентификатор User — намеренное расхождение с `int`-PK монолита
    (ADR TD-01 Фаза 1): identity больше не завязан на автоинкремент БД."""

    value: uuid.UUID

    def __init__(
        self, marker: object = _MISSING, value: uuid.UUID = cast("uuid.UUID", _MISSING)
    ) -> None:
        if marker is not _PRIVATE_MARKER:
            raise RuntimeError(
                "UserId instances must be created through "
                "UserId.new_id()/UserId.create()"
            )
        object.__setattr__(self, "value", value)

    @classmethod
    def new_id(cls) -> "UserId":
        return cls(_PRIVATE_MARKER, uuid.uuid4())

    @classmethod
    def create(cls, value: uuid.UUID) -> "UserId":
        return cls(_PRIVATE_MARKER, value)

    def _equality_components(self) -> tuple[Any, ...]:
        return (self.value,)
