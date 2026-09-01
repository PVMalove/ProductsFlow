import enum
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from kernel_domain.result import Result

from domain.product import Product
from domain.product_id import ProductId
from domain.product_image import ProductImage
from domain.repositories import Cursor, ProductPage


@dataclass(frozen=True)
class Actor:
    """Authenticated caller passed from the HTTP adapter to a use case."""

    user_id: uuid.UUID
    token: str


@dataclass(frozen=True)
class OwnerSnapshot:
    """The owner fields needed by catalog visibility decisions."""

    user_id: uuid.UUID
    role: str
    is_active: bool
    last_applied_outbox_id: int


class OwnerReadModel(Protocol):
    async def get(self, user_id: uuid.UUID) -> OwnerSnapshot | None: ...

    async def upsert(self, owner: OwnerSnapshot) -> None: ...


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
    ) -> ProductPage: ...


__all__ = [
    "Actor",
    "IdentityGateway",
    "IdentityUser",
    "ProductAuditAction",
    "OwnerReadModel",
    "OwnerProjectionWriter",
    "OwnerQueryPort",
    "OwnerSnapshot",
    "ProductCommandPort",
    "ProductImage",
    "ProductImageStorage",
    "ProductAuditEntry",
    "ProductAuditReader",
    "ProductQueryPort",
]
