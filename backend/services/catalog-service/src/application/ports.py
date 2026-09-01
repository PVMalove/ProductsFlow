import enum
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from domain.product_image import ProductImage


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


__all__ = [
    "Actor",
    "IdentityGateway",
    "IdentityUser",
    "ProductAuditAction",
    "OwnerReadModel",
    "OwnerSnapshot",
    "ProductImage",
    "ProductImageStorage",
    "ProductAuditEntry",
    "ProductAuditReader",
]
