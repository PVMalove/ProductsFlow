from catalog.domain.product import Product
from catalog.domain.viewer import Viewer


class ProductVisibilityPolicy:
    """`VisibilityPolicy[Viewer, Product]` (ADR 0003, `kernel_domain.VisibilityPolicy`
    Protocol, issue #149): предикат на уровне самого Товара — активен, или
    видим его Владельцу. Деактивация Владельца (`owner_read_model.is_active`)
    — отдельное, более широкое условие, не свойство `Product`, поэтому здесь
    не проверяется (см. `catalog.infrastructure.security.auth`, где оба
    условия складываются)."""

    def is_visible(self, viewer: Viewer, resource: Product) -> bool:
        if viewer.is_admin:
            return True
        if resource.is_active:
            return True
        return viewer.user_id == resource.user_id
