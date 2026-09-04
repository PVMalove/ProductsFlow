import uuid
from dataclasses import dataclass


@dataclass(frozen=True)
class Viewer:
    """Наблюдатель HTTP-запроса (issue #149): `user_id` — `sub` токена
    identity, локален и не протухает (ADR 0011); `is_admin` — синхронно
    сверенный факт, вычисляется только на ветке, где доступ действительно
    даётся ролью (см. `infrastructure.security.auth`), не кэшируется
    между запросами."""

    user_id: uuid.UUID | None
    is_admin: bool
