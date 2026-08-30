from dataclasses import dataclass

from kernel_domain.domain_event import DomainEvent

from identity.domain.email import Email
from identity.domain.user_id import UserId


@dataclass(frozen=True, kw_only=True)
class UserRegistered(DomainEvent):
    user_id: UserId
    email: Email


@dataclass(frozen=True, kw_only=True)
class PasswordChanged(DomainEvent):
    user_id: UserId


@dataclass(frozen=True, kw_only=True)
class Deactivated(DomainEvent):
    user_id: UserId


@dataclass(frozen=True, kw_only=True)
class Activated(DomainEvent):
    user_id: UserId
