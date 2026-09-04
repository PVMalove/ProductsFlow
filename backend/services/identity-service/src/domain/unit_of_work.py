"""Identity transaction contract (ADR 0034)."""

from typing import Protocol

from kernel_platform.unit_of_work import UnitOfWork

from domain.repositories import UserRepository


class IdentityUnitOfWork(UnitOfWork, Protocol):
    users: UserRepository
