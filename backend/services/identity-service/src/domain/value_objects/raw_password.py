from dataclasses import dataclass
from typing import Any, cast

from kernel_domain.errors import Error, ErrorList
from kernel_domain.result import Result
from kernel_domain.value_object import ValueObject

from domain.errors import IdentityErrors
from domain.value_objects import PRIVATE_MARKER

_MIN_LENGTH = 8

_MISSING = object()


@dataclass(frozen=True, eq=False)
class RawPassword(ValueObject):
    """Пароль до хеширования — стойкость проверяется здесь, на исходной
    строке, а не постфактум над уже вычисленным `password_hash` в `User`:
    хеш почти всегда тривиально проходит правила длины/регистра/цифры
    независимо от свойств исходного пароля, так что проверка над ним была бы
    бессмысленной с реальным хешером."""

    value: str

    def __init__(
        self, marker: object = _MISSING, value: str = cast("str", _MISSING)
    ) -> None:
        if marker is not PRIVATE_MARKER:
            raise RuntimeError(
                "RawPassword instances must be created through RawPassword.create()"
            )
        object.__setattr__(self, "value", value)

    @classmethod
    def create(cls, value: str) -> Result["RawPassword"]:
        error = _validate(value)
        if error is not None:
            return Result[RawPassword].fail(error)
        return Result[RawPassword].ok(cls(PRIVATE_MARKER, value))

    def _equality_components(self) -> tuple[Any, ...]:
        return (self.value,)


def _validate(value: str) -> Error | None:
    errors: list[Error] = []
    if len(value) < _MIN_LENGTH:
        errors.append(IdentityErrors.password_too_short())
    if not any(ch.islower() for ch in value):
        errors.append(IdentityErrors.password_missing_lowercase())
    if not any(ch.isdigit() for ch in value):
        errors.append(IdentityErrors.password_missing_digit())
    if not errors:
        return None
    return ErrorList.of(errors)
