"""Транзакционный контракт cart/checkout (ADR 0006)."""

from typing import Protocol

from kernel_platform.unit_of_work import UnitOfWork

from domain.repositories import (
    CartRepository,
    IdempotencyKeyRepository,
    OrderRepository,
    ReservationOutboxRepository,
)


class CartUnitOfWork(UnitOfWork, Protocol):
    carts: CartRepository


class CheckoutUnitOfWork(UnitOfWork, Protocol):
    """issue #372, D5 — одна локальная транзакция: quote -> Pending Order ->
    Idempotency-Key -> selection freeze -> reservation_outbox intent, все
    репозитории на одной сессии. Также переиспользуется reservation-result
    handler'ом воркера (`orders`+`carts`, issue #372 D7)."""

    carts: CartRepository
    orders: OrderRepository
    idempotency_keys: IdempotencyKeyRepository
    reservation_outbox: ReservationOutboxRepository
