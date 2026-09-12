# ruff: noqa: E501
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Literal, cast

from kernel_domain import PRIVATE_MARKER
from kernel_domain.entity import Entity
from kernel_domain.result import Result

from domain.errors import InventoryErrors
from domain.events.reservation_domain_event import InventoryReleased, InventoryReserved
from domain.reservation_status import ReservationStatus

_MISSING = object()


class ReservationLineStatus(Enum):
    CONFIRMED = "confirmed"
    UNAVAILABLE = "unavailable"


@dataclass
class ReservationLine:
    """Дочерняя сущность строки резерва — plain dataclass с голым
    `uuid.UUID` id, тот же прецедент, что `CartLine`/`TicketMessage` (issue
    #369, архитектурный бриф #370 находка 11). Несёт обе ветки D4: и
    подтверждённые, и недоступные строки живут в одном списке, различённые
    только `status`."""

    id: uuid.UUID
    product_id: uuid.UUID
    quantity: int
    status: ReservationLineStatus


class Reservation(Entity[uuid.UUID]):
    """Агрегат резерва остатка под заказ (issue #370, ADR 0016). PK =
    `order_id` (D3) — закрепляет «один активный резерв на заказ» уже на
    уровне схемы, тот же прецедент, что `Inventory` (issue #367, находка 10)
    и `Cart` (issue #369, D3).

    Конструктор вызывается только через `create()` (новый резерв) или
    `reconstitute()` (гидратация из БД)."""

    def __init__(
        self,
        marker: object = _MISSING,
        id: uuid.UUID = cast("uuid.UUID", _MISSING),
        *,
        status: ReservationStatus,
        lines: list[ReservationLine],
        expires_at: datetime,
        created_at: datetime,
    ) -> None:
        super().__init__(marker, id=id)
        self.status = status
        self.lines = lines
        self.expires_at = expires_at
        self.created_at = created_at

    @classmethod
    def create(
        cls,
        order_id: uuid.UUID,
        *,
        lines: list[ReservationLine],
        ttl_minutes: int,
        now: datetime,
    ) -> "Reservation":
        """Партиционирование confirmed/unavailable уже сделано вызывающим
        (application-слой, D4/D8) — без `Result`: создание резерва само по
        себе не проваливается по бизнес-правилу, частичное подтверждение —
        нормальный результат (AC2), не ошибка."""
        expires_at = now + timedelta(minutes=ttl_minutes)
        reservation = cls(
            PRIVATE_MARKER,
            order_id,
            status=ReservationStatus.ACTIVE,
            lines=lines,
            expires_at=expires_at,
            created_at=now,
        )
        reservation.add_domain_event(
            InventoryReserved(
                order_id=order_id,
                expires_at=expires_at,
                confirmed_lines=tuple(
                    (line.product_id, line.quantity)
                    for line in lines
                    if line.status is ReservationLineStatus.CONFIRMED
                ),
                unavailable_lines=tuple(
                    (line.product_id, line.quantity)
                    for line in lines
                    if line.status is ReservationLineStatus.UNAVAILABLE
                ),
            )
        )
        return reservation

    @classmethod
    def reconstitute(
        cls,
        order_id: uuid.UUID,
        *,
        status: ReservationStatus,
        lines: list[ReservationLine],
        expires_at: datetime,
        created_at: datetime,
    ) -> "Reservation":
        return cls(
            PRIVATE_MARKER,
            order_id,
            status=status,
            lines=lines,
            expires_at=expires_at,
            created_at=created_at,
        )

    def release(self, *, reason: Literal["manual", "expired"]) -> Result[None]:
        """Идемпотентный guard — второй, business-result слой идемпотентности
        (D3/находка 6, независимый от `inbox_messages`-гейта #365): повторный
        release уже неактивного резерва — `Result.fail`, не исключение,
        легитимный повтор не должен уехать в DLQ."""
        if self.status is not ReservationStatus.ACTIVE:
            return Result[None].fail(InventoryErrors.reservation_not_active())

        self.status = (
            ReservationStatus.RELEASED
            if reason == "manual"
            else ReservationStatus.EXPIRED
        )
        confirmed_lines = tuple(
            (line.product_id, line.quantity)
            for line in self.lines
            if line.status is ReservationLineStatus.CONFIRMED
        )
        self.add_domain_event(
            InventoryReleased(
                order_id=self.id, reason=reason, released_lines=confirmed_lines
            )
        )
        return Result[None].ok(None)
