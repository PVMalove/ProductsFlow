from kernel_domain.errors import ErrorType

from domain.errors import CatalogErrors


def test_invalid_name_carries_stable_code_and_public_field() -> None:
    error = CatalogErrors.invalid_name(3, 100)

    assert error.code == "invalid_name"
    assert error.type is ErrorType.VALIDATION
    assert error.invalid_field == "name"
    assert error.description == "Название должно быть от 3 до 100 символов"


def test_invalid_category_carries_stable_code_and_public_field() -> None:
    error = CatalogErrors.invalid_category(3, 100)

    assert error.code == "invalid_category"
    assert error.type is ErrorType.VALIDATION
    assert error.invalid_field == "category"
    assert error.description == "Категория должна быть от 3 до 100 символов"


def test_invalid_price_carries_stable_code_and_public_field() -> None:
    error = CatalogErrors.invalid_price()

    assert error.code == "invalid_price"
    assert error.type is ErrorType.VALIDATION
    assert error.invalid_field == "price"
    assert error.description == "Цена не может быть отрицательной"


def test_already_active_carries_stable_code_without_a_field() -> None:
    error = CatalogErrors.already_active()

    assert error.code == "already_active"
    assert error.type is ErrorType.CONFLICT
    assert error.invalid_field is None
    assert error.description == "Товар уже активен"


def test_already_deactivated_carries_stable_code_without_a_field() -> None:
    error = CatalogErrors.already_deactivated()

    assert error.code == "already_deactivated"
    assert error.type is ErrorType.CONFLICT
    assert error.invalid_field is None
    assert error.description == "Товар уже деактивирован"


def test_invalid_quantity_carries_stable_code_and_public_field() -> None:
    error = CatalogErrors.invalid_quantity()

    assert error.code == "invalid_quantity"
    assert error.type is ErrorType.VALIDATION
    assert error.invalid_field == "quantity"
    assert error.description == "Количество должно быть положительным целым числом"


def test_checkout_quote_hidden_carries_stable_code_without_a_field() -> None:
    error = CatalogErrors.checkout_quote_hidden()

    assert error.code == "checkout_quote_hidden"
    assert error.type is ErrorType.NOT_FOUND
    assert error.invalid_field is None
    assert error.description == "Товар недоступен для оформления"


def test_checkout_quote_inactive_carries_stable_code_without_a_field() -> None:
    error = CatalogErrors.checkout_quote_inactive()

    assert error.code == "checkout_quote_inactive"
    assert error.type is ErrorType.CONFLICT
    assert error.invalid_field is None
    assert error.description == "Товар деактивирован"
