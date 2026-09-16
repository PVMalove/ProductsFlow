"""Единый реестр ожидаемых Result-ошибок cart/order domain/application (ADR
0014, issue #369/#372). Используется только domain и application —
infrastructure сюда не обращается."""

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

    @staticmethod
    def line_locked() -> Error:
        """Строка вошла в Checkout Selection активного заказа и не может
        мутироваться до терминального результата Saga (issue #372, D3/AC5)."""
        return Error.conflict(
            "line_locked",
            "Строка корзины заблокирована активным оформлением заказа",
        )


class OrderErrors:
    @staticmethod
    def empty_cart() -> Error:
        """Checkout пустой/несуществующей корзины отклоняется до любого
        обращения к Catalog (issue #372, D5)."""
        return Error.validation(
            "empty_cart",
            "Корзина пуста — оформление заказа невозможно",
        )

    @staticmethod
    def idempotency_key_conflict() -> Error:
        """Повтор `Idempotency-Key` с изменившимся составом корзины
        (issue #372, D2 — буквальная HTTP Idempotency-Key семантика)."""
        return Error.conflict(
            "idempotency_key_conflict",
            "Idempotency-Key уже использован с другим содержимым корзины",
        )
