from abc import abstractmethod
from functools import total_ordering
from typing import Any

from kernel_domain.value_object import ValueObject


@total_ordering
class ComparableValueObject(ValueObject):
    """Объект-значение с полным порядком (по образцу
    CSharpFunctionalExtensions.ComparableValueObject): сравнение —
    покомпонентно по `_comparable_equality_components()`, до первой
    различающейся пары; разные типы упорядочены по имени типа."""

    @abstractmethod
    def _comparable_equality_components(self) -> tuple[Any, ...]: ...

    def _equality_components(self) -> tuple[Any, ...]:
        return self._comparable_equality_components()

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, ComparableValueObject):
            return NotImplemented
        if type(other) is not type(self):
            return type(self).__name__ < type(other).__name__
        for left, right in zip(
            self._comparable_equality_components(),
            other._comparable_equality_components(),
        ):
            if left != right:
                return bool(left < right)
        return False
