import uuid

from catalog.domain.product import Product
from catalog.domain.product_id import ProductId
from catalog.domain.viewer import Viewer
from catalog.domain.visibility import ProductVisibilityPolicy

OWNER_ID = uuid.uuid4()
OTHER_ID = uuid.uuid4()


def _product(*, is_active: bool) -> Product:
    result = Product.create(
        ProductId(1),
        name="Название товара",
        description="Описание",
        price=10.0,
        category="Категория",
        user_id=OWNER_ID,
    )
    assert result.is_ok
    product = result.value
    product.pull_events()
    if not is_active:
        product.deactivate()
        product.pull_events()
    return product


def test_active_product_is_visible_to_anonymous_viewer() -> None:
    policy = ProductVisibilityPolicy()
    viewer = Viewer(user_id=None, is_admin=False)

    assert policy.is_visible(viewer, _product(is_active=True)) is True


def test_deactivated_product_is_hidden_from_anonymous_viewer() -> None:
    policy = ProductVisibilityPolicy()
    viewer = Viewer(user_id=None, is_admin=False)

    assert policy.is_visible(viewer, _product(is_active=False)) is False


def test_deactivated_product_is_hidden_from_a_different_authenticated_viewer() -> None:
    policy = ProductVisibilityPolicy()
    viewer = Viewer(user_id=OTHER_ID, is_admin=False)

    assert policy.is_visible(viewer, _product(is_active=False)) is False


def test_deactivated_product_is_visible_to_its_owner() -> None:
    policy = ProductVisibilityPolicy()
    viewer = Viewer(user_id=OWNER_ID, is_admin=False)

    assert policy.is_visible(viewer, _product(is_active=False)) is True


def test_deactivated_product_is_visible_to_an_admin() -> None:
    policy = ProductVisibilityPolicy()
    viewer = Viewer(user_id=OTHER_ID, is_admin=True)

    assert policy.is_visible(viewer, _product(is_active=False)) is True
