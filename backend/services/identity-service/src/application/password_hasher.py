from typing import Protocol


class PasswordHasher(Protocol):
    """Порт хеширования пароля (ADR TD-01 Фаза 1) — реальный bcrypt-адаптер
    остаётся инфраструктурой Фазы 2; домен и application-слой видят только
    этот контракт."""

    def hash(self, password: str) -> str: ...

    def verify(self, password: str, password_hash: str) -> bool: ...
