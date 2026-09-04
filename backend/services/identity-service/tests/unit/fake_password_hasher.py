from application.password_hasher import PasswordHasher

_PREFIX = "hashed::"


class FakePasswordHasher(PasswordHasher):
    """Детерминированный фейк-хешер для тестов (ADR TD-01 Фаза 1) — никакого
    реального bcrypt."""

    def hash(self, password: str) -> str:
        return f"{_PREFIX}{password}"

    def verify(self, password: str, password_hash: str) -> bool:
        return password_hash == self.hash(password)
