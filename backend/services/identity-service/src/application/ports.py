"""Application-порты, разделяющие command- и query-стороны identity."""

import enum
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from kernel_platform.pagination import Cursor, OffsetPage, Page

from domain.role import Role
from domain.value_objects.email import Email
from domain.value_objects.user_id import UserId


@dataclass(frozen=True)
class UserReadModel:
    """Неизменяемая проекция, возвращаемая read-стороной identity."""

    id: UserId
    email: Email
    role: Role
    is_active: bool


UserPage = Page[UserReadModel]


class UserQueryPort(Protocol):
    """Доступ только для чтения к read-модели identity."""

    async def get_by_id(self, user_id: UserId) -> UserReadModel | None: ...


class UserListQueryPort(Protocol):
    """Доступ только для чтения к курсорно-пагинированным пользователям."""

    async def list(
        self,
        *,
        limit: int,
        after: Cursor | None = None,
        before: Cursor | None = None,
    ) -> UserPage: ...


class UserAuditAction(enum.StrEnum):
    """Действия, фиксируемые в неизменяемом audit trail User."""

    REGISTERED = "registered"
    PASSWORD_CHANGED = "password_changed"
    ACTIVATED = "activated"
    DEACTIVATED = "deactivated"
    ROLE_CHANGED = "role_changed"
    DELETED = "deleted"


@dataclass(frozen=True)
class UserAuditEntry:
    """Read-модель одной неизменяемой audit-записи User."""

    id: int
    user_id: UserId
    actor_user_id: UserId
    action: UserAuditAction
    description: str
    created_at: datetime


UserAuditPage = OffsetPage[UserAuditEntry]


class UserAuditQueryPort(Protocol):
    """Доступ только для чтения к audit-записям User."""

    async def list_all(self, *, page_index: int, page_size: int) -> UserAuditPage: ...

    async def get_by_user(self, user_id: UserId) -> list[UserAuditEntry]: ...


class PasswordHasher(Protocol):
    """Порт хеширования пароля; реализации принадлежат infrastructure."""

    def hash(self, password: str) -> str: ...

    def verify(self, password: str, password_hash: str) -> bool: ...
