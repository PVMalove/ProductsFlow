from typing import Protocol

from identity.domain.email import Email
from identity.domain.user import User


class UserRepository(Protocol):
    """Порт персистентности User (ADR TD-01 Фаза 1) — без реальной БД до
    Фазы 2; реализация в этой части — только in-memory фейк для тестов."""

    def exists_by_email(self, email: Email) -> bool: ...

    def add(self, user: User) -> None: ...
