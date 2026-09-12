# ruff: noqa: E501
"""Команда и handler для `inventory.reserve.v1` (issue #370, D1/D4/D8) —
message-driven use case, НЕ FastAPI-CQRS форма `AdjustInventoryStockCommandHandler`
(issue #367): никакого UoW/`.commit()` здесь — транзакцией управляет
`consume_command` через сессию, переданную вызывающим адаптером
(`api/reservation_commands.py`), тот же приём, что `handle_product_event`
(issue #367, находка 3)."""

import uuid
from dataclasses import dataclass
from datetime import datetime

from domain.entities.reservation import (
    Reservation,
    ReservationLine,
    ReservationLineStatus,
)
from domain.repositories import InventoryRepository, ReservationRepository


@dataclass(frozen=True)
class ReservationLineRequest:
    product_id: uuid.UUID
    quantity: int


@dataclass(frozen=True)
class ReserveInventoryLinesCommand:
    order_id: uuid.UUID
    lines: tuple[ReservationLineRequest, ...]


class ReserveInventoryLinesCommandHandler:
    """
    Business Logic Summary

    Context & Purpose: Резервирует строки заказа под остаток на этапе checkout.
    Validations: `order_id` уже имеет резерв (business-layer идемпотентность, D3/находка 6) — no-op, ничего не мутирует.
    Side Effects: `Inventory.reserved` растёт по каждой подтверждённой строке; создаётся `Reservation` (+ `InventoryReserved` в outbox через `try_create`).
    """

    def __init__(
        self,
        inventory_repo: InventoryRepository,
        reservation_repo: ReservationRepository,
        *,
        ttl_minutes: int,
    ) -> None:
        self._inventory_repo = inventory_repo
        self._reservation_repo = reservation_repo
        self._ttl_minutes = ttl_minutes

    async def execute(
        self, command: ReserveInventoryLinesCommand, *, now: datetime
    ) -> None:
        existing = await self._reservation_repo.get_by_order_id(command.order_id)
        if existing is not None:
            return

        # D4: сортировка по product_id — предотвращает deadlock между двумя
        # одновременными командами, задевающими пересекающиеся множества
        # товаров в разном порядке.
        lines: list[ReservationLine] = []
        for request in sorted(command.lines, key=lambda line: line.product_id):
            result = await self._inventory_repo.reserve(
                request.product_id, request.quantity
            )
            status = (
                ReservationLineStatus.CONFIRMED
                if result is not None and result.is_ok
                else ReservationLineStatus.UNAVAILABLE
            )
            lines.append(
                ReservationLine(
                    id=uuid.uuid4(),
                    product_id=request.product_id,
                    quantity=request.quantity,
                    status=status,
                )
            )

        reservation = Reservation.create(
            command.order_id, lines=lines, ttl_minutes=self._ttl_minutes, now=now
        )
        created = await self._reservation_repo.try_create(reservation)
        if created:
            return

        # Risk 6 архитектурного брифа: настоящая гонка двух разных
        # command_id для одного order_id (несколько реплик воркера) —
        # try_create конфликтует ПОСЛЕ того, как мы уже мутировали
        # Inventory.reserved. Компенсируем, чтобы проигравшая попытка не
        # оставила reserved навсегда завышенным.
        for line in lines:
            if line.status is ReservationLineStatus.CONFIRMED:
                await self._inventory_repo.release(line.product_id, line.quantity)
