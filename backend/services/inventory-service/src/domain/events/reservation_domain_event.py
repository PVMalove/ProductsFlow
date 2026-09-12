# ruff: noqa: E501
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from kernel_domain.domain_event import DomainEvent

# Поля ниже нарочно несут примитивные `(product_id, quantity)`-пары, не
# `domain.entities.reservation.ReservationLine` — событие не должно тянуть за
# собой сущность (циклический импорт `reservation.py` <-> этот модуль),
# и вообще не обязано знать про дочернюю сущность как таковую (D1, архитектурный
# бриф #370).


@dataclass(frozen=True, kw_only=True)
class InventoryReserved(DomainEvent):
    """Один факт на КАЖДЫЙ `inventory.reserve.v1`, независимо от того,
    подтверждены все строки, частично или ни одной (D1, AC2) — покрывает
    все три исхода единым событием."""

    aggregate_type: str = "Reservation"
    event_type: str = "inventory.reserved.v1"

    order_id: uuid.UUID
    expires_at: datetime
    confirmed_lines: tuple[tuple[uuid.UUID, int], ...]
    unavailable_lines: tuple[tuple[uuid.UUID, int], ...]

    def aggregate_id(self) -> uuid.UUID:
        return self.order_id

    def to_payload(self) -> dict[str, Any]:
        return {
            "order_id": str(self.order_id),
            "expires_at": self.expires_at.isoformat(),
            "confirmed_lines": [
                {"product_id": str(product_id), "quantity": quantity}
                for product_id, quantity in self.confirmed_lines
            ],
            "unavailable_lines": [
                {"product_id": str(product_id), "requested_quantity": quantity}
                for product_id, quantity in self.unavailable_lines
            ],
        }


@dataclass(frozen=True, kw_only=True)
class InventoryReleased(DomainEvent):
    """Один тип на оба сценария релиза — явный `inventory.release.v1` и
    автоматическое TTL-истечение (D1): структурный эффект для Order
    идентичен («эти строки снова свободны»), `reason` даёт достаточную
    дифференциацию без удвоения wire-поверхности."""

    aggregate_type: str = "Reservation"
    event_type: str = "inventory.released.v1"

    order_id: uuid.UUID
    reason: str
    released_lines: tuple[tuple[uuid.UUID, int], ...]

    def aggregate_id(self) -> uuid.UUID:
        return self.order_id

    def to_payload(self) -> dict[str, Any]:
        return {
            "order_id": str(self.order_id),
            "reason": self.reason,
            "released_lines": [
                {"product_id": str(product_id), "quantity": quantity}
                for product_id, quantity in self.released_lines
            ],
        }
