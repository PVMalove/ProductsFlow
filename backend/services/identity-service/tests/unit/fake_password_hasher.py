from identity.application.password_hasher import PasswordHasher


class FakePasswordHasher(PasswordHasher):
    """Детерминированный фейк-хешер для тестов (ADR TD-01 Фаза 1) — никакого
    реального bcrypt. Разворот строки (не префикс/не константа) сохраняет
    длину и состав символов пароля, так что проверки стойкости пароля в
    `User.register()` остаются осмысленными при прогоне через команду."""

    def hash(self, password: str) -> str:
        return password[::-1]

    def verify(self, password: str, password_hash: str) -> bool:
        return password_hash == self.hash(password)
