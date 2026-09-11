"""Стабильность публичного контракта ошибок inventory (ADR 0014, issue #367)."""

from kernel_domain.errors import ErrorType

from domain.errors import InventoryErrors


def test_negative_stock_adjustment_is_a_stable_conflict_error() -> None:
    error = InventoryErrors.negative_stock_adjustment()

    assert error.code == "negative_stock_adjustment"
    assert error.type is ErrorType.CONFLICT
    assert error.description
    assert error.invalid_field is None


def test_inventory_not_found_is_a_stable_not_found_error() -> None:
    error = InventoryErrors.inventory_not_found()

    assert error.code == "inventory_not_found"
    assert error.type is ErrorType.NOT_FOUND
    assert error.description
