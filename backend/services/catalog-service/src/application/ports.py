# ruff: noqa: E501
import enum
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from kernel_domain.result import Result
from kernel_platform.pagination import Page

from application.search_cursor import ProductSortOption, SearchCursor
from application.search_snapshot import ProductSearchSnapshot, ProductSearchTombstone
from contracts.product import ProductView
from domain.entities.product import Product
from domain.product_image import ProductImage
from domain.repositories import Cursor, ProductPage
from domain.value_objects.product_id import ProductId


@dataclass(frozen=True)
class Actor:
    """Аутентифицированный вызывающий, передаваемый из HTTP-адаптера в use case."""

    user_id: uuid.UUID
    token: str


@dataclass(frozen=True)
class OwnerSnapshot:
    """Поля владельца, нужные для решений о видимости в catalog."""

    user_id: uuid.UUID
    role: str
    is_active: bool
    last_applied_outbox_id: int


class OwnerReadModel(Protocol):
    async def get(self, user_id: uuid.UUID) -> OwnerSnapshot | None: ...

    async def upsert(self, owner: OwnerSnapshot) -> None: ...

    async def find_by_role(self, role: str) -> OwnerSnapshot | None: ...


class OwnerQueryPort(Protocol):
    async def get(self, user_id: uuid.UUID) -> OwnerSnapshot | None: ...


class OwnerProjectionWriter(Protocol):
    async def upsert(self, owner: OwnerSnapshot) -> None: ...


@dataclass(frozen=True)
class IdentityUser:
    id: uuid.UUID
    role: str
    is_active: bool


class IdentityGateway(Protocol):
    async def fetch_current_user(self, token: str) -> IdentityUser: ...


class ProductImageStorage(Protocol):
    async def put_object(
        self, bucket_name: str, key: str, body: bytes, content_type: str
    ) -> None: ...

    async def delete_object(self, bucket_name: str, key: str) -> None: ...

    async def build_presigned_url(
        self, bucket_name: str, key: str, expires_in: int = 3600
    ) -> str: ...


class ProductAuditAction(enum.StrEnum):
    CREATED = "created"
    UPDATED = "updated"
    DELETED = "deleted"
    ACTIVATED = "activated"
    DEACTIVATED = "deactivated"
    IMAGE_UPDATED = "image_updated"
    IMAGE_DELETED = "image_deleted"


@dataclass(frozen=True)
class ProductAuditEntry:
    id: int
    product_id: uuid.UUID
    actor_user_id: uuid.UUID | None
    action: ProductAuditAction
    description: str
    created_at: datetime


class ProductAuditReader(Protocol):
    async def get_by_product(
        self, product_id: uuid.UUID
    ) -> list[ProductAuditEntry]: ...


class ProductCommandPort(Protocol):
    async def get_by_id(self, product_id: ProductId) -> Product | None: ...

    async def create(
        self,
        *,
        name: str,
        description: str,
        price: float,
        category: str,
        user_id: uuid.UUID,
    ) -> Result[Product]: ...

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


class ProductQueryPort(Protocol):
    async def get_by_id(self, product_id: ProductId) -> Product | None: ...

    async def get_product_image(self, product_id: ProductId) -> ProductImage | None: ...

    async def list(
        self,
        *,
        limit: int,
        after: Cursor | None = None,
        before: Cursor | None = None,
        category: str | None = None,
        min_price: float | None = None,
        max_price: float | None = None,
    ) -> ProductPage: ...


class ProductSearchPort(Protocol):
    """Read-side port for the public Product search index."""

    async def search(
        self,
        query: str,
        *,
        category: str | None = None,
        min_price: float | None = None,
        max_price: float | None = None,
        sort: ProductSortOption = ProductSortOption.RELEVANCE,
        limit: int = 20,
        cursor: SearchCursor | None = None,
    ) -> Page[ProductView]: ...


class ProductSearchIndexer(Protocol):
    async def index(
        self, snapshot: ProductSearchSnapshot, *, owner_is_active: bool
    ) -> None: ...

    async def delete(self, tombstone: ProductSearchTombstone) -> None: ...

    async def set_owner_active(
        self, user_id: uuid.UUID, *, is_active: bool
    ) -> None: ...


class ProductSearchReindexer(ProductSearchIndexer, Protocol):
    """Index writer lifecycle for a zero-downtime rebuild."""

    async def begin_reindex(self) -> None: ...

    async def index_rebuild(
        self, snapshot: ProductSearchSnapshot, *, owner_is_active: bool
    ) -> None: ...

    async def complete_reindex(self) -> None: ...


@dataclass(frozen=True)
class SearchSnapshotWithOwner:
    snapshot: ProductSearchSnapshot
    owner_is_active: bool


class ProductSearchSnapshotSource(Protocol):
    async def get(self, product_id: uuid.UUID) -> SearchSnapshotWithOwner | None: ...

    def stream_batches(
        self, *, batch_size: int
    ) -> AsyncIterator[list[SearchSnapshotWithOwner]]: ...


@dataclass(frozen=True)
class OwnerSearchState:
    """Durable Owner visibility flag maintained by `catalog-search-worker`
    from Identity lifecycle events (issue #288). A missing row means the
    worker has not yet observed this owner and must be treated as inactive
    (deny-by-default) — never resolved via a synchronous Identity call, unlike
    `OwnerReadModel`."""

    user_id: uuid.UUID
    is_active: bool
    last_applied_outbox_id: int


class OwnerSearchStateStore(Protocol):
    async def get(self, user_id: uuid.UUID) -> OwnerSearchState | None: ...

    async def upsert(self, state: OwnerSearchState) -> bool:
        """Returns whether `state` was actually applied — `False` for a
        stale/duplicate event (see `last_applied_outbox_id` versioning,
        ADR 0011)."""
        ...


__all__ = [
    "Actor",
    "IdentityGateway",
    "IdentityUser",
    "ProductAuditAction",
    "OwnerReadModel",
    "OwnerProjectionWriter",
    "OwnerQueryPort",
    "OwnerSnapshot",
    "OwnerSearchState",
    "OwnerSearchStateStore",
    "ProductCommandPort",
    "ProductImage",
    "ProductImageStorage",
    "ProductAuditEntry",
    "ProductAuditReader",
    "ProductQueryPort",
    "ProductSearchPort",
    "ProductSearchIndexer",
    "ProductSearchReindexer",
    "ProductSearchSnapshotSource",
    "SearchSnapshotWithOwner",
]
