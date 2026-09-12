# ruff: noqa: E501
"""Команда и handler для `inventory.release.v1` (issue #370, D1/D7/D8) —
message-driven use case, тот же приём, что `reserve_inventory_lines.py`:
никакого UoW/`.commit()`. Общий handler для ДВУХ сценариев release (явный
manual через команду и автоматический TTL-sweep, D6/D1) — оба вызывают этот
же `execute()` с разным `reason`, разница структурного эффекта для Order
только в поле `reason` outbox-факта."""

import uuid
from dataclasses import dataclass
from typing import Literal

from domain.entities.reservation import ReservationLineStatus
from domain.repositories import InventoryRepository, ReservationRepository

ReleaseReason = Literal["manual", "expired"]


@dataclass(frozen=True)
class ReleaseInventoryReservationCommand:
    order_id: uuid.UUID
    reason: ReleaseReason


class ReleaseInventoryReservationCommandHandler:
    """
    Business Logic Summary

    Context & Purpose: Освобождает резерв целиком (D7 — весь заказ, не отдельные строки) вручную или по истечении TTL.
    Validations: несуществующий/уже неактивный резерв — no-op, не исключение (легитимный повтор не должен уехать в DLQ).
    Side Effects: `Inventory.reserved` уменьшается по подтверждённым строкам; `Reservation` переходит в RELEASED/EXPIRED (+ `InventoryReleased` в outbox через `save()`).
    """

    def __init__(
        self,
        inventory_repo: InventoryRepository,
        reservation_repo: ReservationRepository,
    ) -> None:
        self._inventory_repo = inventory_repo
        self._reservation_repo = reservation_repo

    async def execute(self, command: ReleaseInventoryReservationCommand) -> None:
        reservation = await self._reservation_repo.get_by_order_id(command.order_id)
        if reservation is None:
            return

        result = reservation.release(reason=command.reason)
        if result.is_err:
            return

        confirmed_lines = sorted(
            (
                line
                for line in reservation.lines
                if line.status is ReservationLineStatus.CONFIRMED
            ),
            key=lambda line: line.product_id,
        )
        for line in confirmed_lines:
            await self._inventory_repo.release(line.product_id, line.quantity)

        await self._reservation_repo.save(reservation)
