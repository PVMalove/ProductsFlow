"""Транзакционный контракт cart (ADR 0006)."""

from typing import Protocol

from kernel_platform.unit_of_work import UnitOfWork

from domain.repositories import CartRepository


class CartUnitOfWork(UnitOfWork, Protocol):
    carts: CartRepository
