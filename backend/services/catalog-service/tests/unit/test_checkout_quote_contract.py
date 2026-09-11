import uuid

from contracts.checkout_quote import CheckoutQuoteView
from domain.entities.product import Product
from domain.value_objects.product_id import ProductId


def _product() -> Product:
    result = Product.create(
        ProductId.new_id(),
        name="Товар",
        description="Описание товара",
        price=19.99,
        category="Категория",
        user_id=uuid.uuid4(),
    )
    assert result.is_ok
    return result.value


def test_checkout_quote_view_from_domain_converts_price_and_carries_quantity() -> None:
    product = _product()

    view = CheckoutQuoteView.from_domain(product, quantity=3)

    assert view.product_id == product.id.value
    assert view.description == "Описание товара"
    assert view.unit_price_kopecks == 1999
    assert isinstance(view.unit_price_kopecks, int)
    assert view.quantity == 3
    assert view.discount_amount == 0
