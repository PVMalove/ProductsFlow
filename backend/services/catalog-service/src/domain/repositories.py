import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, runtime_checkable

from kernel_domain.result import Result

from domain.product import Product
from domain.product_id import ProductId


@dataclass(frozen=True)
class Cursor:
    """Keyset-позиция в списке продуктов."""

    created_at: datetime
    id: int


@dataclass(frozen=True)
class PageInfo:
    next_cursor: str | None
    prev_cursor: str | None
    has_more: bool
    has_prev: bool


@dataclass(frozen=True)
class ProductPage:
    items: list[Product]
    page_info: PageInfo


@runtime_checkable
class ProductRepository(Protocol):
    """Контракт персистентности агрегата Product (ADR 0023)."""

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
