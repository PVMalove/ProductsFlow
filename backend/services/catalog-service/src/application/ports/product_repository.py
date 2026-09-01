import uuid
from typing import Protocol, runtime_checkable

from kernel_domain.result import Result

from application.pagination import Cursor, ProductPage
from domain.product import Product
from domain.product_id import ProductId


@runtime_checkable
class ProductRepository(Protocol):
    """Persistence operations required by catalog product use cases."""

    async def create(
        self,
        *,
        name: str,
        description: str,
        price: float,
        category: str,
        user_id: uuid.UUID,
    ) -> Result[Product]: ...

    async def get_by_id(self, product_id: ProductId) -> Product | None: ...

    async def update(
        self,
        product_id: ProductId,
        *,
        name: str | None = None,
        description: str | None = None,
        price: float | None = None,
        category: str | None = None,
    ) -> Result[Product] | None: ...

    async def activate(self, product_id: ProductId) -> Result[Product] | None: ...

    async def deactivate(self, product_id: ProductId) -> Result[Product] | None: ...

    async def delete(self, product_id: ProductId) -> Product | None: ...

    async def list(
        self,
        *,
        limit: int,
        after: Cursor | None = None,
        before: Cursor | None = None,
    ) -> ProductPage: ...
