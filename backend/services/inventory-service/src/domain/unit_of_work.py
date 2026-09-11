"""Транзакционный контракт inventory (ADR 0006)."""

from typing import Protocol

from kernel_platform.unit_of_work import UnitOfWork

from domain.repositories import InventoryRepository


class InventoryUnitOfWork(UnitOfWork, Protocol):
    inventory: InventoryRepository
