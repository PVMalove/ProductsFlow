from typing import Protocol

from domain.email import Email
from domain.user import User
from domain.user_id import UserId


class UserRepository(Protocol):
    """Persistence contract for the identity domain's User aggregate."""

    def exists_by_email(self, email: Email) -> bool: ...

    def get_by_email(self, email: Email) -> User | None: ...

    def get_by_id(self, user_id: UserId) -> User | None: ...

    def add(self, user: User) -> None: ...

    def save(self, user: User) -> None: ...
