from abc import ABC, abstractmethod
from typing import Any


class ValueObject(ABC):
    """Объект-значение (по образцу CSharpFunctionalExtensions.ValueObject):
    равенство и хэш — по значению компонентов из `_equality_components()`,
    не по идентичности. Разные типы никогда не равны, даже с одинаковыми
    компонентами."""

    @abstractmethod
    def _equality_components(self) -> tuple[Any, ...]: ...

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, ValueObject) or type(other) is not type(self):
            return False
        return self._equality_components() == other._equality_components()

    def __hash__(self) -> int:
        return hash((type(self), self._equality_components()))
