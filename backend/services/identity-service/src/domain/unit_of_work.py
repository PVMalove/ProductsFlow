"""Транзакционный контракт identity (ADR 0006)."""

from typing import Protocol

from kernel_platform.unit_of_work import UnitOfWork

from domain.repositories import UserRepository


class IdentityUnitOfWork(UnitOfWork, Protocol):
    users: UserRepository
