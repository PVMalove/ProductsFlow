from identity.application.user_repository import UserRepository
from identity.domain.email import Email
from identity.domain.user import User


class FakeUserRepository(UserRepository):
    """In-memory фейк UserRepository для тестов application-слоя (ADR TD-01
    Фаза 1) — никакой реальной БД, только dict в памяти."""

    def __init__(self) -> None:
        self.users: dict[str, User] = {}

    def exists_by_email(self, email: Email) -> bool:
        return email.value in self.users

    def add(self, user: User) -> None:
        self.users[user.email.value] = user
