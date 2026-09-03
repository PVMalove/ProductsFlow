"""Framework-independent output contracts for identity BFF endpoints
(ADR 0033) — application handlers return these, HTTP only serializes them."""

import uuid
from dataclasses import dataclass

from application.ports import UserReadModel
from domain.role import Role
from domain.user import User


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
