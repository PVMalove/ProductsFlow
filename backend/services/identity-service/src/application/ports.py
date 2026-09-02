"""Application ports used to keep identity command and query sides separate."""

from dataclasses import dataclass
from typing import Protocol

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


class UserQueryPort(Protocol):
    """Read-only access to the identity read model."""

    async def get_by_id(self, user_id: UserId) -> UserReadModel | None: ...


class PasswordHasher(Protocol):
    """Port for password hashing; implementations belong to infrastructure."""

    def hash(self, password: str) -> str: ...

    def verify(self, password: str, password_hash: str) -> bool: ...
