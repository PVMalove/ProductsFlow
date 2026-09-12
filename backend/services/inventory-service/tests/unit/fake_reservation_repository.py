"""Фейковый ReservationRepository для юнит-тестов reservation-хендлеров
(issue #370)."""

import uuid
from datetime import datetime

from domain.entities.reservation import Reservation


class FakeReservationRepository:
    def __init__(self, reservations: list[Reservation] | None = None) -> None:
        self._by_order_id: dict[uuid.UUID, Reservation] = {
            reservation.id: reservation for reservation in (reservations or [])
        }
        self.try_create_calls: list[Reservation] = []
        self.save_calls: list[Reservation] = []
        # Тестовый рубильник (Risk 6 брифа): форсирует конфликт try_create,
        # даже если get_by_order_id ещё не видел резерв — симулирует
        # настоящую гонку двух разных command_id для одного order_id.
        self.force_try_create_conflict = False

    async def get_by_order_id(self, order_id: uuid.UUID) -> Reservation | None:
        return self._by_order_id.get(order_id)

    async def try_create(self, reservation: Reservation) -> bool:
        self.try_create_calls.append(reservation)
        if self.force_try_create_conflict or reservation.id in self._by_order_id:
            return False
        self._by_order_id[reservation.id] = reservation
        return True

    async def claim_expired(self, *, now: datetime, limit: int) -> list[Reservation]:
        raise NotImplementedError

    async def save(self, reservation: Reservation) -> None:
        self.save_calls.append(reservation)
        self._by_order_id[reservation.id] = reservation
