"""`domain/errors.py::CartErrors` (архитектурный бриф issue #369, Seams for
TDD #2) — код/description/`ErrorType` стабильны."""

from kernel_domain.errors import ErrorType

from domain.errors import CartErrors


def test_invalid_quantity_is_a_validation_error_on_quantity_field() -> None:
    error = CartErrors.invalid_quantity()

    assert error.code == "invalid_quantity"
    assert error.type is ErrorType.VALIDATION
    assert error.invalid_field == "quantity"


def test_line_not_found_is_a_not_found_error() -> None:
    error = CartErrors.line_not_found()

    assert error.code == "line_not_found"
    assert error.type is ErrorType.NOT_FOUND
