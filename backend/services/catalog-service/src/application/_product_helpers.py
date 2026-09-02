"""Small application helpers shared by product command and query handlers."""

import uuid

from application.errors import ProductNotFoundError
from application.ports import ProductCommandPort
from domain.product import Product
from domain.product_id import ProductId


async def get_product(repository: ProductCommandPort, product_id: uuid.UUID) -> Product:
    product = await repository.get_by_id(ProductId(product_id))
    if product is None:
        raise ProductNotFoundError
    return product
