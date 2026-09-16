from enum import Enum


class ReservationStatus(Enum):
    """Жизненный цикл `Reservation` (issue #370, ADR 0016; ALLOCATED — issue
    #373, тот же ADR). По образцу `support-service`'s
    `domain/ticket_status.py`."""

    ACTIVE = "active"
    ALLOCATED = "allocated"
    RELEASED = "released"
    EXPIRED = "expired"
