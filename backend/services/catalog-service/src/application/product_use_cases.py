"""Compatibility adapters for the pre-CQRS product use-case imports."""

from application.commands import (
    ActivateProductCommandHandler as ActivateProduct,
)
from application.commands import (
    CreateProductCommandHandler as CreateProduct,
)
from application.commands import (
    DeactivateProductCommandHandler as DeactivateProduct,
)
from application.commands import (
    DeleteProductCommandHandler as DeleteProduct,
)
from application.commands import (
    UpdateProductCommandHandler as UpdateProduct,
)
from application.queries import (
    GetProductAuditQueryHandler as GetProductAudit,
)
from application.queries import (
    GetProductQueryHandler as GetProduct,
)
from application.queries import (
    ListProductsQueryHandler as ListProducts,
)

__all__ = [
    "ActivateProduct",
    "CreateProduct",
    "DeactivateProduct",
    "DeleteProduct",
    "GetProduct",
    "GetProductAudit",
    "ListProducts",
    "UpdateProduct",
]
