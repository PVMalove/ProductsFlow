from domain.email import Email
from domain.repositories import UserRepository
from domain.user import User
from domain.user_id import UserId


class FakeUserRepository(UserRepository):
    """In-memory фейк UserRepository для тестов application-слоя (ADR TD-01
    Фаза 1) — никакой реальной БД, только dict в памяти."""

    def __init__(self) -> None:
        self.users: dict[str, User] = {}

    async def exists_by_email(self, email: Email) -> bool:
        return email.value in self.users

    async def get_by_email(self, email: Email) -> User | None:
        return self.users.get(email.value)

    async def get_by_id(self, user_id: UserId) -> User | None:
        for user in self.users.values():
            if user.id == user_id:
                return user
        return None

    async def add(self, user: User) -> None:
        self.users[user.email.value] = user

    async def save(self, user: User) -> None:
        self.users[user.email.value] = user
