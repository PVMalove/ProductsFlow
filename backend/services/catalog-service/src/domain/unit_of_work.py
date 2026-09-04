"""Транзакционный контракт catalog (ADR 0006)."""

from typing import Protocol

from kernel_platform.unit_of_work import UnitOfWork

from domain.repositories import ProductRepository


class CatalogUnitOfWork(UnitOfWork, Protocol):
    products: ProductRepository
