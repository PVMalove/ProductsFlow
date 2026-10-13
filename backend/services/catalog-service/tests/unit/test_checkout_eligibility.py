import uuid

from domain.checkout_eligibility import evaluate_checkout_eligibility
from domain.entities.product import Product
from domain.value_objects.product_id import ProductId


def _product(*, is_active: bool = True) -> Product:
    result = Product.create(
        ProductId.new_id(),
        name="Товар",
        description="Описание",
        price=10.0,
        category="Категория",
        user_id=uuid.uuid4(),
    )
    assert result.is_ok
    product = result.value
    if not is_active:
        deactivated = product.deactivate()
        assert deactivated.is_ok
    return product


def test_active_product_with_active_owner_is_eligible() -> None:
    product = _product(is_active=True)

    error = evaluate_checkout_eligibility(product, owner_is_active=True)

    assert error is None


def test_deactivated_product_is_not_eligible() -> None:
    product = _product(is_active=False)

    error = evaluate_checkout_eligibility(product, owner_is_active=True)

    assert error is not None
    assert error.code == "checkout_quote_inactive"


def test_product_with_deactivated_owner_is_hidden() -> None:
    product = _product(is_active=True)

    error = evaluate_checkout_eligibility(product, owner_is_active=False)

    assert error is not None
    assert error.code == "checkout_quote_hidden"


def test_deactivated_owner_takes_precedence_over_deactivated_product() -> None:
    product = _product(is_active=False)

    error = evaluate_checkout_eligibility(product, owner_is_active=False)

    assert error is not None
    assert error.code == "checkout_quote_hidden"
