import re
from dataclasses import dataclass
from typing import Any, cast

from kernel_domain.errors import Error, ErrorType
from kernel_domain.result import Result
from kernel_domain.value_object import ValueObject

from domain.value_objects import _PRIVATE_MARKER

_EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

_MISSING = object()


@dataclass(frozen=True, eq=False)
class Email(ValueObject):
    """Value object для email — заменяет `username` монолита как
    логин/уникальность-идентификатор (ADR TD-01 Фаза 1)."""

    value: str

    def __init__(
        self, marker: object = _MISSING, value: str = cast("str", _MISSING)
    ) -> None:
        if marker is not _PRIVATE_MARKER:
            raise RuntimeError("Email instances must be created through Email.create()")
        object.__setattr__(self, "value", value)

    @classmethod
    def create(cls, value: str) -> Result["Email"]:
        if not _EMAIL_PATTERN.match(value):
            return Result[Email].fail(
                Error(
                    code="invalid_email",
                    description=f"Некорректный email: {value!r}",
                    type=ErrorType.VALIDATION,
                )
            )
        return Result[Email].ok(cls(_PRIVATE_MARKER, value))

    def _equality_components(self) -> tuple[Any, ...]:
        return (self.value,)
