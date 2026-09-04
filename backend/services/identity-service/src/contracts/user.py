"""Framework-independent контракты вывода для BFF-эндпоинтов identity
(ADR 0002) — application-хендлеры возвращают их, HTTP только сериализует."""

import uuid
from dataclasses import dataclass

from application.ports import UserReadModel
from domain.entities.user import User
from domain.role import Role


@dataclass(frozen=True)
class UserView:
    id: uuid.UUID
    email: str
    role: Role
    is_active: bool

    @classmethod
    def from_user(cls, user: "User | UserReadModel") -> "UserView":
        return cls(
            id=user.id.value,
            email=user.email.value,
            role=user.role,
            is_active=user.is_active,
        )
