"""Единый реестр ожидаемых Result-ошибок inventory domain/application
(ADR 0014, issue #367). Используется только domain и application —
infrastructure сюда не обращается."""

from kernel_domain.errors import Error


class InventoryErrors:
    @staticmethod
    def negative_stock_adjustment() -> Error:
        """Нарушение зависит от текущего состояния агрегата (остаток после
        применения `delta` ушёл бы в минус), не от формы входа — тот же
        класс, что `CatalogErrors.already_active()`, поэтому `conflict`
        (409), не `validation`."""
        return Error.conflict(
            "negative_stock_adjustment",
            "Итоговый остаток не может быть отрицательным",
        )

    @staticmethod
    def inventory_not_found() -> Error:
        return Error.not_found(
            "inventory_not_found",
            "Остаток товара не найден",
        )

    @staticmethod
    def insufficient_available_stock() -> Error:
        """Инвариант `reserve()`/`release()` (issue #370): нарушение зависит
        от текущего состояния агрегата (доступный остаток = quantity -
        reserved), не от формы входа — тот же класс, что
        `negative_stock_adjustment()`, поэтому `conflict` (409)."""
        return Error.conflict(
            "insufficient_available_stock",
            "Недостаточно доступного остатка для резервирования",
        )

    @staticmethod
    def reservation_not_active() -> Error:
        """Идемпотентный guard `Reservation.release()` (issue #370, D3/находка
        6): повторный release уже неактивного резерва — не исключение, а
        ожидаемый `Result.fail`."""
        return Error.conflict(
            "reservation_not_active",
            "Резерв не находится в активном состоянии",
        )
