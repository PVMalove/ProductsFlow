"""Framework-independent output contracts for identity BFF endpoints
(ADR 0033) — application handlers return these, HTTP only serializes them."""

import uuid
from dataclasses import dataclass

from kernel_domain.result import Result

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


def user_view_result(result: Result[User]) -> Result[UserView]:
    """Map a command handler's `Result[User]` to the BFF-facing
    `Result[UserView]` — shared by `api/auth.py` and `api/users.py` so the
    conversion isn't duplicated per router."""
    if result.is_err:
        return Result.fail(result.error)
    return Result.ok(UserView.from_user(result.value))
