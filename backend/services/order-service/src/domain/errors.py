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

    @staticmethod
    def order_not_found() -> Error:
        """`order_id` не существует вовсе (issue #377, D5)."""
        return Error.not_found("order_not_found", "Заказ не найден")

    @staticmethod
    def order_access_denied() -> Error:
        """`order_id` существует, но принадлежит другому пользователю (issue
        #377, D5 — то же разделение 404/403, что у строк корзины)."""
        return Error.forbidden("order_access_denied", "Нет прав на этот заказ")

    @staticmethod
    def order_not_cancellable() -> Error:
        """Отмена допустима только для `PENDING` Order до запроса capture
        (issue #377, D1/R1, ADR 0016)."""
        return Error.conflict(
            "order_not_cancellable",
            "Заказ нельзя отменить в текущем состоянии: отмена возможна "
            "только до запроса списания оплаты",
        )
