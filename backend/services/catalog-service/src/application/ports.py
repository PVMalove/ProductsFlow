import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from domain.repositories import ProductRepository


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


@dataclass(frozen=True)
class ProductAuditEntry:
    id: int
    product_id: int
    actor_user_id: int | None
    action: str
    description: str
    created_at: datetime


class ProductAuditReader(Protocol):
    async def get_by_product(self, product_id: int) -> list[ProductAuditEntry]: ...


__all__ = [
    "Actor",
    "IdentityGateway",
    "IdentityUser",
    "OwnerReadModel",
    "OwnerSnapshot",
    "ProductAuditEntry",
    "ProductAuditReader",
    "ProductRepository",
]
