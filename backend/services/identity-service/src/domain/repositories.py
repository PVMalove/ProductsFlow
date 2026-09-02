from typing import Protocol, runtime_checkable

from domain.email import Email
from domain.user import User
from domain.user_id import UserId


@runtime_checkable
class UserRepository(Protocol):
    """Persistence contract for the identity domain's User aggregate."""

    async def exists_by_email(self, email: Email) -> bool: ...

    async def get_by_email(self, email: Email) -> User | None: ...

    async def get_by_id(self, user_id: UserId) -> User | None: ...

    async def add(self, user: User) -> None: ...

    async def save(self, user: User) -> None: ...
