"""Единый реестр ожидаемых Result-ошибок cart domain/application (ADR 0014,
issue #369). Используется только domain и application — infrastructure сюда
не обращается."""

from kernel_domain.errors import Error


class CartErrors:
    @staticmethod
    def invalid_quantity() -> Error:
        """Текст идентичен `CatalogErrors.invalid_quantity()` (архитектурный
        бриф issue #369, D7) — переиспользуем формулировку, не изобретаем
        новую."""
        return Error.validation(
            "invalid_quantity",
            "Количество должно быть положительным целым числом",
            invalid_field="quantity",
        )

    @staticmethod
    def line_not_found() -> Error:
        """Используется только доменом для внутренней логики поиска строки в
        списке — HTTP-уровневый 404 для «строки нет вовсе» идёт через
        `CartLineNotFoundError` (архитектурный бриф issue #369, D7)."""
        return Error.not_found(
            "line_not_found",
            "Строка корзины не найдена",
        )
