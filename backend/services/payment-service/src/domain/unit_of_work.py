"""Транзакционный контракт payment (ADR 0006)."""

from typing import Protocol

from kernel_platform.unit_of_work import UnitOfWork

from domain.repositories import PaymentAuthorizationRepository


class PaymentUnitOfWork(UnitOfWork, Protocol):
    payments: PaymentAuthorizationRepository
