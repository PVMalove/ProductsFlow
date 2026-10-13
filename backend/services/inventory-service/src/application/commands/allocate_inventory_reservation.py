# ruff: noqa: E501
"""Команда и handler для `inventory.allocate.v1` (issue #373, ADR 0016) —
message-driven use case, тот же приём, что `release_inventory_reservation.py`:
никакого UoW/`.commit()`. В отличие от release, allocate НЕ трогает
`InventoryRepository` вовсе — `Inventory.reserved` уже учитывает живой резерв
независимо от ACTIVE/ALLOCATED (архитектурное решение issue #373), поэтому
хендлер зависит только от `ReservationRepository` — сама сигнатура
конструктора доказывает отсутствие побочного эффекта на остаток."""

import uuid
from dataclasses import dataclass

from domain.repositories import ReservationRepository


@dataclass(frozen=True)
class AllocateInventoryReservationCommand:
    order_id: uuid.UUID


class AllocateInventoryReservationCommandHandler:
    """
    Business Logic Summary

    Context & Purpose: Переводит живой резерв заказа целиком из ACTIVE в ALLOCATED.
    Validations: несуществующий/уже неактивный (не ACTIVE) резерв — no-op, не исключение (легитимный повтор не должен уехать в DLQ).
    Side Effects: `Reservation` переходит в ALLOCATED (+ `InventoryAllocated` в outbox через `save()`). `Inventory.reserved` не меняется.
    """

    def __init__(self, reservation_repo: ReservationRepository) -> None:
        self._reservation_repo = reservation_repo

    async def execute(self, command: AllocateInventoryReservationCommand) -> None:
        reservation = await self._reservation_repo.get_by_order_id(command.order_id)
        if reservation is None:
            return

        result = reservation.allocate()
        if result.is_err:
            return

        await self._reservation_repo.save(reservation)
