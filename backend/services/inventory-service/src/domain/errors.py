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
