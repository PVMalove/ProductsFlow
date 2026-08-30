from typing import Protocol

from identity.domain.email import Email
from identity.domain.user import User
from identity.domain.user_id import UserId


class UserRepository(Protocol):
    """Порт персистентности User (ADR TD-01 Фаза 1) — без реальной БД до
    Фазы 2; реализация в этой части — только in-memory фейк для тестов."""

    def exists_by_email(self, email: Email) -> bool: ...

    def get_by_email(self, email: Email) -> User | None: ...

    def get_by_id(self, user_id: UserId) -> User | None: ...

    def add(self, user: User) -> None: ...

    def save(self, user: User) -> None: ...
