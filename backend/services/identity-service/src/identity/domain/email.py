import re
from dataclasses import dataclass
from typing import Any

from kernel_domain.value_object import ValueObject

_EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


@dataclass(frozen=True, eq=False)
class Email(ValueObject):
    """Value object для email — заменяет `username` монолита как
    логин/уникальность-идентификатор (ADR TD-01 Фаза 1)."""

    value: str

    def __post_init__(self) -> None:
        if not _EMAIL_PATTERN.match(self.value):
            raise ValueError(f"Некорректный email: {self.value!r}")

    def _equality_components(self) -> tuple[Any, ...]:
        return (self.value,)
