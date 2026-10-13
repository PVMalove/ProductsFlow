from kernel_domain.errors import Error

from domain.entities.product import Product
from domain.errors import CatalogErrors


def evaluate_checkout_eligibility(
    product: Product, *, owner_is_active: bool
) -> Error | None:
    """Checkout eligibility (issue #366) — строже видимости
    (`ProductVisibilityPolicy`): даже владелец/админ не получает quote на
    деактивированный товар, поэтому не принимает `Viewer`. Чистая функция без
    I/O. Порядок проверок фиксирован: деактивация Владельца — более широкое
    условие ("скрыт"), проверяется раньше состояния самого товара."""
    if not owner_is_active:
        return CatalogErrors.checkout_quote_hidden()
    if not product.is_active:
        return CatalogErrors.checkout_quote_inactive()
    return None
