import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, runtime_checkable

from kernel_domain.result import Result

from domain.product import Product
from domain.product_id import ProductId
from domain.product_image import ProductImage


@dataclass(frozen=True)
class Cursor:
    """Keyset-позиция в списке продуктов."""

    created_at: datetime
    id: uuid.UUID


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

    async def get_product_image(self, product_id: ProductId) -> ProductImage | None: ...

    async def upsert_product_image(
        self,
        product_id: ProductId,
        *,
        s3_key: str,
        content_type: str,
        size_bytes: int,
        actor_user_id: uuid.UUID,
    ) -> ProductImage: ...

    async def delete_product_image(
        self, product_id: ProductId, *, actor_user_id: uuid.UUID
    ) -> None: ...

    async def list(
        self,
        *,
        limit: int,
        after: Cursor | None = None,
        before: Cursor | None = None,
    ) -> ProductPage: ...
