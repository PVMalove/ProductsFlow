import uuid
from dataclasses import dataclass
from typing import Any

from kernel_domain.domain_event import DomainEvent

from domain.role import Role
from domain.value_objects.email import Email
from domain.value_objects.user_id import UserId


@dataclass(frozen=True, kw_only=True)
class UserEvent(DomainEvent):
    """Общий контракт событий агрегата User для transactional outbox."""

    aggregate_type: str = "User"
    user_id: UserId

    def aggregate_id(self) -> uuid.UUID:
        return self.user_id.value

    def to_payload(self) -> dict[str, Any]:
        return {"user_id": str(self.user_id.value)}


@dataclass(frozen=True, kw_only=True)
class UserRegistered(UserEvent):
    event_type: str = "user.registered.v1"
    email: Email

    def to_payload(self) -> dict[str, Any]:
        return {**super().to_payload(), "email": self.email.value}


@dataclass(frozen=True, kw_only=True)
class PasswordChanged(UserEvent):
    event_type: str = "user.password_changed.v1"


@dataclass(frozen=True, kw_only=True)
class Deactivated(UserEvent):
    event_type: str = "user.deactivated.v1"


@dataclass(frozen=True, kw_only=True)
class Deleted(UserEvent):
    event_type: str = "user.deleted.v1"


@dataclass(frozen=True, kw_only=True)
class Activated(UserEvent):
    event_type: str = "user.activated.v1"


@dataclass(frozen=True, kw_only=True)
class RoleChanged(UserEvent):
    event_type: str = "user.role_changed.v1"
    role: Role

    def to_payload(self) -> dict[str, Any]:
        return {**super().to_payload(), "role": self.role.value}
