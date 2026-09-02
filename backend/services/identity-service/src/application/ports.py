"""Application ports used to keep identity command and query sides separate."""

import enum
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from kernel_platform.pagination import Cursor, PageInfo

from domain.email import Email
from domain.role import Role
from domain.user_id import UserId


@dataclass(frozen=True)
class UserReadModel:
    """Immutable projection returned by the identity read side."""

    id: UserId
    email: Email
    role: Role
    is_active: bool


@dataclass(frozen=True)
class UserPage:
    """A cursor-paginated page of users."""

    items: list[UserReadModel]
    page_info: PageInfo


class UserQueryPort(Protocol):
    """Read-only access to the identity read model."""

    async def get_by_id(self, user_id: UserId) -> UserReadModel | None: ...


class UserListQueryPort(Protocol):
    """Read-only access to cursor-paginated users."""

    async def list(
        self,
        *,
        limit: int,
        after: Cursor | None = None,
        before: Cursor | None = None,
    ) -> UserPage: ...


class UserAuditAction(enum.StrEnum):
    """Actions recorded in the immutable User audit trail."""

    REGISTERED = "registered"
    PASSWORD_CHANGED = "password_changed"
    ACTIVATED = "activated"
    DEACTIVATED = "deactivated"
    ROLE_CHANGED = "role_changed"


@dataclass(frozen=True)
class UserAuditEntry:
    """Read model for one immutable User audit record."""

    id: int
    user_id: UserId
    actor_user_id: UserId
    action: UserAuditAction
    description: str
    created_at: datetime


@dataclass(frozen=True)
class UserAuditPage:
    """Offset-paginated page for the global User audit feed."""

    items: list[UserAuditEntry]
    page_index: int
    page_size: int
    total: int
    total_pages: int


class UserAuditQueryPort(Protocol):
    """Read-only access to User audit records."""

    async def list_all(self, *, page_index: int, page_size: int) -> UserAuditPage: ...

    async def get_by_user(self, user_id: UserId) -> list[UserAuditEntry]: ...


class PasswordHasher(Protocol):
    """Port for password hashing; implementations belong to infrastructure."""

    def hash(self, password: str) -> str: ...

    def verify(self, password: str, password_hash: str) -> bool: ...
