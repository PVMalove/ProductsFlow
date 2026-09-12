from enum import Enum


class ReservationStatus(Enum):
    """Жизненный цикл `Reservation` (issue #370, ADR 0016). По образцу
    `support-service`'s `domain/ticket_status.py`."""

    ACTIVE = "active"
    RELEASED = "released"
    EXPIRED = "expired"
