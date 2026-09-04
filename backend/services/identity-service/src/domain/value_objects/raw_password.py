from dataclasses import dataclass
from typing import Any, cast

from kernel_domain.errors import Error, ErrorType
from kernel_domain.result import Result
from kernel_domain.value_object import ValueObject

_MIN_LENGTH = 8

_PRIVATE_MARKER = object()
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
        if marker is not _PRIVATE_MARKER:
            raise RuntimeError(
                "RawPassword instances must be created through RawPassword.create()"
            )
        object.__setattr__(self, "value", value)

    @classmethod
    def create(cls, value: str) -> Result["RawPassword"]:
        error = _validate(value)
        if error is not None:
            return Result[RawPassword].fail(error)
        return Result[RawPassword].ok(cls(_PRIVATE_MARKER, value))

    def _equality_components(self) -> tuple[Any, ...]:
        return (self.value,)


def _validate(value: str) -> Error | None:
    if len(value) < _MIN_LENGTH:
        return Error(
            code="password_too_short",
            description="Пароль должен содержать минимум 8 символов",
            type=ErrorType.VALIDATION,
        )
    if not any(ch.islower() for ch in value):
        return Error(
            code="password_missing_lowercase",
            description="Пароль должен содержать строчную букву",
            type=ErrorType.VALIDATION,
        )
    if not any(ch.isdigit() for ch in value):
        return Error(
            code="password_missing_digit",
            description="Пароль должен содержать цифру",
            type=ErrorType.VALIDATION,
        )
    return None
