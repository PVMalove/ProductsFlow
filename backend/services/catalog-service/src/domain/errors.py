"""Единый реестр ожидаемых Result-ошибок catalog domain/application (ADR 0014).

Устраняет сырые конструкторы `Error(...)` в пользу стабильных `snake_case`
кодов, безопасных описаний и публичных `invalid_field`. Используется только
domain и application — infrastructure сюда не обращается."""

from kernel_domain.errors import Error


class CatalogErrors:
    @staticmethod
    def invalid_name(min_length: int, max_length: int) -> Error:
        return Error.validation(
            "invalid_name",
            f"Название должно быть от {min_length} до {max_length} символов",
            invalid_field="name",
        )

    @staticmethod
    def invalid_category(min_length: int, max_length: int) -> Error:
        return Error.validation(
            "invalid_category",
            f"Категория должна быть от {min_length} до {max_length} символов",
            invalid_field="category",
        )

    @staticmethod
    def invalid_price() -> Error:
        return Error.validation(
            "invalid_price",
            "Цена не может быть отрицательной",
            invalid_field="price",
        )

    @staticmethod
    def already_active() -> Error:
        return Error.conflict("already_active", "Товар уже активен")

    @staticmethod
    def already_deactivated() -> Error:
        return Error.conflict("already_deactivated", "Товар уже деактивирован")

    @staticmethod
    def invalid_quantity() -> Error:
        return Error.validation(
            "invalid_quantity",
            "Количество должно быть положительным целым числом",
            invalid_field="quantity",
        )

    @staticmethod
    def checkout_quote_hidden() -> Error:
        return Error.not_found(
            "checkout_quote_hidden", "Товар недоступен для оформления"
        )

    @staticmethod
    def checkout_quote_inactive() -> Error:
        return Error.conflict("checkout_quote_inactive", "Товар деактивирован")
