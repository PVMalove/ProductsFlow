"""Application ports used to keep identity command and query sides separate."""

from typing import Protocol

from domain.email import Email
from domain.user import User
from domain.user_id import UserId


class UserQueryPort(Protocol):
    """Read-only access to the identity read model."""

    def get_by_id(self, user_id: UserId) -> User | None: ...

    def get_by_email(self, email: Email) -> User | None: ...


class UserCommandPort(Protocol):
    """Persistence boundary required by identity command handlers."""

    def exists_by_email(self, email: Email) -> bool: ...

    def get_by_email(self, email: Email) -> User | None: ...

    def get_by_id(self, user_id: UserId) -> User | None: ...

    def add(self, user: User) -> None: ...

    def save(self, user: User) -> None: ...


class PasswordHasher(Protocol):
    """Port for password hashing; implementations belong to infrastructure."""

    def hash(self, password: str) -> str: ...

    def verify(self, password: str, password_hash: str) -> bool: ...
